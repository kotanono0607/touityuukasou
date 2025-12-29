#!/usr/bin/env python3
"""
generate_video.py - 画像と音声を結合して動画を生成

使用方法:
    python scripts/generate_video.py [--episode N] [--dry-run]

オプション:
    --episode N       指定エピソードのみ処理
    --dry-run         ffmpegを実行せずにコマンドを表示
    --burn-subtitles  字幕を動画に焼き付け
    --with-bgm        BGMをミックス

必要:
    ffmpeg (コマンドラインツール)

出力:
    outputs/video/episode{N}.mp4
    outputs/video/episode{N}.srt (字幕)
"""

import argparse
import json
import subprocess
import wave
from pathlib import Path
from typing import Optional


def load_json(filepath: Path) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_audio_duration(audio_path: Path) -> float:
    """WAVファイルの長さを秒で取得"""
    try:
        with wave.open(str(audio_path), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 3.0  # デフォルト3秒


def get_video_duration(video_path: Path) -> float:
    """動画の長さを秒で取得"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def get_bgm_for_episode(episode_num: int, base_dir: Path) -> Optional[dict]:
    """エピソードに適したBGMを取得"""
    bgm_json_path = base_dir / "data" / "bgm.json"
    if not bgm_json_path.exists():
        return None

    bgm_data = load_json(bgm_json_path)
    tracks = bgm_data.get("tracks", {})

    # エピソード別のデフォルトBGM
    episode_bgm = {
        1: "office_ambient",  # 導入、遺失物取扱所
        2: "emotional_sad",   # 澄香の物語
        3: "flashback",       # 回想シーン中心
        4: "determination",   # クライマックス
    }

    track_id = episode_bgm.get(episode_num, "main_theme")
    track = tracks.get(track_id)

    if track:
        bgm_path = base_dir / track.get("file", "")
        if bgm_path.exists():
            return {
                "path": bgm_path,
                "volume": track.get("volume", 0.3),
                "name": track.get("name", track_id),
            }

    return None


def mix_bgm_with_video(
    video_path: Path,
    bgm_path: Path,
    output_path: Path,
    bgm_volume: float = 0.3,
    dry_run: bool = False,
) -> bool:
    """動画にBGMをミックス"""
    if not video_path.exists() or not bgm_path.exists():
        return False

    video_duration = get_video_duration(video_path)
    if video_duration <= 0:
        return False

    # BGMをループしつつ、動画の音声（セリフ）とミックス
    # amixフィルタで音声をミックス、BGMは音量を下げる
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1",  # BGMを無限ループ
        "-i", str(bgm_path),
        "-filter_complex",
        f"[1:a]volume={bgm_volume},afade=t=in:st=0:d=2,afade=t=out:st={video_duration-3}:d=3[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(video_duration),
        str(output_path)
    ]

    if dry_run:
        print(f"  [DRY-RUN] BGMミックス: {bgm_path.name} → {output_path.name}")
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            error_lines = result.stderr.strip().split('\n')
            last_lines = '\n'.join(error_lines[-5:])
            print(f"  BGMミックスエラー:\n{last_lines}")
        return result.returncode == 0
    except Exception as e:
        print(f"  BGMミックスエラー: {e}")
        return False


# キャラクター名の日本語マッピング
SPEAKER_NAMES = {
    "ren": "灰谷",
    "yuki": "雪",
    "sumika": "澄香",
    "sumika_young": "澄香（若）",
    "mother": "母",
    "mother_young": "母（若）",
    "father": "父",
    "voice_entity": "声の怪異",
    "narrator": "ナレーション",
}


def format_srt_time(seconds: float) -> str:
    """秒をSRT形式の時間に変換 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(scripts: list, audio_dir: Path, output_path: Path) -> list:
    """字幕ファイル(SRT)を生成し、タイミング情報を返す"""
    srt_lines = []
    timing_info = []
    current_time = 0.0
    subtitle_index = 1

    for script in scripts:
        scene_id = script.get("scene_id", "unknown")
        beat_index = script.get("beat_index", 0)
        text = script.get("text", "")
        speaker = script.get("speaker", "")

        if not text:
            continue

        # 音声ファイルから長さを取得
        audio_file = audio_dir / f"{scene_id}_{beat_index:03d}.wav"
        if audio_file.exists():
            duration = get_audio_duration(audio_file)
        else:
            duration = max(2.0, len(text) * 0.15)  # 音声がなければテキスト長から推定

        start_time = current_time
        end_time = current_time + duration

        # SRTエントリ作成（日本語キャラクター名を使用）
        speaker_name = SPEAKER_NAMES.get(speaker, speaker) if speaker else ""
        if speaker_name:
            speaker_prefix = f"【{speaker_name}】"
        else:
            speaker_prefix = ""
        srt_lines.append(f"{subtitle_index}")
        srt_lines.append(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}")
        srt_lines.append(f"{speaker_prefix}{text}")
        srt_lines.append("")

        # タイミング情報を保存
        timing_info.append({
            "scene_id": scene_id,
            "beat_index": beat_index,
            "start": start_time,
            "end": end_time,
            "duration": duration,
        })

        current_time = end_time
        subtitle_index += 1

    # SRTファイル書き出し
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    return timing_info


def create_scene_video(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    duration: float,
    dry_run: bool = False,
) -> bool:
    """1シーン分の動画を作成（画像+音声）"""

    if audio_path.exists():
        # 音声あり: 画像を音声の長さに合わせる
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-t", str(duration + 0.5),  # 少し余裕を持たせる
            str(output_path)
        ]
    else:
        # 音声なし: 固定長の無音動画
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-an",
            str(output_path)
        ]

    if dry_run:
        print(f"    [DRY-RUN] {' '.join(cmd[:10])}...")
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            error_lines = result.stderr.strip().split('\n')
            last_lines = '\n'.join(error_lines[-5:])
            print(f"    ffmpegエラー:\n{last_lines}")
        return result.returncode == 0
    except Exception as e:
        print(f"    エラー: {e}")
        return False


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, dry_run: bool = False) -> bool:
    """字幕を動画に焼き付け"""
    if not video_path.exists() or not srt_path.exists():
        return False

    # SRTパスをスラッシュに変換（ffmpegのsubtitlesフィルター用）
    srt_escaped = str(srt_path.absolute()).replace('\\', '/').replace(':', '\\:')

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{srt_escaped}':force_style='FontSize=24,FontName=Yu Gothic,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2'",
        "-c:a", "copy",
        str(output_path)
    ]

    if dry_run:
        print(f"  [DRY-RUN] 字幕焼き付け: {output_path.name}")
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            error_lines = result.stderr.strip().split('\n')
            last_lines = '\n'.join(error_lines[-5:])
            print(f"  字幕焼き付けエラー:\n{last_lines}")
        return result.returncode == 0
    except Exception as e:
        print(f"  字幕焼き付けエラー: {e}")
        return False


def concatenate_videos(video_list: list, output_path: Path, dry_run: bool = False) -> bool:
    """複数の動画を結合"""
    if not video_list:
        return False

    # 結合リストファイル作成（絶対パスを使用）
    list_file = output_path.parent / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for video in video_list:
            # Windowsパスのバックスラッシュをスラッシュに変換
            video_path = str(video.absolute()).replace('\\', '/')
            f.write(f"file '{video_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path)
    ]

    if dry_run:
        print(f"  [DRY-RUN] 結合: {len(video_list)}本 → {output_path.name}")
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=output_path.parent,
            timeout=300,
        )
        if result.returncode != 0:
            # エラーの最後の部分を表示（実際のエラー内容）
            error_lines = result.stderr.strip().split('\n')
            last_lines = '\n'.join(error_lines[-10:])
            print(f"  結合エラー:\n{last_lines}")
        # リストファイル削除
        list_file.unlink(missing_ok=True)
        return result.returncode == 0
    except Exception as e:
        print(f"  結合エラー: {e}")
        return False


def process_episode(
    episode_num: int,
    base_dir: Path,
    dry_run: bool = False,
    burn_subs: bool = False,
    with_bgm: bool = False,
) -> bool:
    """1エピソードの動画を生成"""

    scripts_path = base_dir / "prompts" / "tts" / f"episode{episode_num}_scripts.json"
    images_dir = base_dir / "outputs" / "images" / f"episode{episode_num}"
    audio_dir = base_dir / "outputs" / "audio" / f"episode{episode_num}"
    video_dir = base_dir / "outputs" / "video"
    temp_dir = video_dir / "temp"

    if not scripts_path.exists():
        print(f"  スクリプトファイルなし: {scripts_path}")
        return False

    temp_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    # スクリプト読み込み
    data = load_json(scripts_path)
    scripts = data.get("scripts", [])

    print(f"  スクリプト数: {len(scripts)}")

    # 字幕生成
    srt_path = video_dir / f"episode{episode_num}.srt"
    timing_info = generate_srt(scripts, audio_dir, srt_path)
    print(f"  字幕生成: {srt_path.name}")

    # シーンごとに動画作成
    scene_videos = []
    current_image = None

    for i, timing in enumerate(timing_info):
        scene_id = timing["scene_id"]
        beat_index = timing["beat_index"]
        duration = timing["duration"]

        # 画像を探す（同じシーンの画像を使い回す）
        image_path = images_dir / f"{scene_id}_{beat_index:03d}.png"
        if image_path.exists():
            current_image = image_path
        elif current_image is None:
            # 最初の画像を探す
            for img in sorted(images_dir.glob("*.png")):
                current_image = img
                break

        if current_image is None:
            print(f"    [{i+1}] 画像なし、スキップ")
            continue

        audio_path = audio_dir / f"{scene_id}_{beat_index:03d}.wav"
        temp_video = temp_dir / f"scene_{i:04d}.mp4"

        print(f"  [{i+1}/{len(timing_info)}] {scene_id}_{beat_index:03d} ({duration:.1f}s)")

        success = create_scene_video(
            image_path=current_image,
            audio_path=audio_path,
            output_path=temp_video,
            duration=duration,
            dry_run=dry_run,
        )

        if success and not dry_run:
            scene_videos.append(temp_video)
        elif dry_run:
            scene_videos.append(temp_video)

    # 動画を結合
    if scene_videos:
        output_path = video_dir / f"episode{episode_num}.mp4"
        print(f"  結合中: {len(scene_videos)}シーン → {output_path.name}")
        success = concatenate_videos(scene_videos, output_path, dry_run)

        if success:
            print(f"  結合完了: {output_path}")
            # 一時ファイル削除
            if not dry_run:
                for v in scene_videos:
                    v.unlink(missing_ok=True)

            current_video = output_path

            # BGMミックス
            if with_bgm:
                bgm_info = get_bgm_for_episode(episode_num, base_dir)
                if bgm_info:
                    print(f"  BGMミックス中: {bgm_info['name']}")
                    bgm_output = video_dir / f"episode{episode_num}_bgm.mp4"
                    if mix_bgm_with_video(
                        current_video,
                        bgm_info["path"],
                        bgm_output,
                        bgm_info["volume"],
                        dry_run,
                    ):
                        print(f"  BGMミックス完了")
                        current_video = bgm_output
                    else:
                        print(f"  BGMミックス失敗、BGMなしで続行")
                else:
                    print(f"  BGMファイルなし、スキップ")

            # 字幕焼き付け
            if burn_subs:
                subtitled_path = video_dir / f"episode{episode_num}_subtitled.mp4"
                print(f"  字幕焼き付け中...")
                if burn_subtitles(current_video, srt_path, subtitled_path, dry_run):
                    print(f"  完成: {subtitled_path}")
                else:
                    print(f"  字幕焼き付け失敗")
            else:
                print(f"  完成: {current_video}")

            return True

    return False


def main():
    parser = argparse.ArgumentParser(description="画像と音声から動画を生成")
    parser.add_argument("--episode", type=int, help="指定エピソードのみ処理")
    parser.add_argument("--dry-run", action="store_true", help="ffmpegを実行せずに確認")
    parser.add_argument("--burn-subtitles", action="store_true", help="字幕を動画に焼き付け")
    parser.add_argument("--with-bgm", action="store_true", help="BGMをミックス")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # ffmpeg確認
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            print("エラー: ffmpegが見つかりません")
            print("  インストール: https://ffmpeg.org/download.html")
            return
    except FileNotFoundError:
        print("エラー: ffmpegがインストールされていません")
        print("  Windows: winget install ffmpeg")
        print("  Mac: brew install ffmpeg")
        return

    print("動画生成を開始します...")
    if args.dry_run:
        print("(ドライラン: ffmpegは実行しません)")
    if args.with_bgm:
        print("(BGMをミックスします)")
    if args.burn_subtitles:
        print("(字幕を動画に焼き付けます)")
    print()

    for episode_num in range(1, 5):
        if args.episode and episode_num != args.episode:
            continue

        print(f"エピソード{episode_num}:")
        success = process_episode(
            episode_num,
            base_dir,
            args.dry_run,
            args.burn_subtitles,
            args.with_bgm,
        )
        if success:
            print(f"  完了")
        else:
            print(f"  失敗またはスキップ")
        print()


if __name__ == "__main__":
    main()
