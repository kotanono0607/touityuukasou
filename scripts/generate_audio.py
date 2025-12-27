#!/usr/bin/env python3
"""
generate_audio.py - Google Text-to-Speech APIを使用して音声を生成

使用方法:
    python scripts/generate_audio.py [--dry-run] [--episode N] [--limit N]

オプション:
    --dry-run    APIを呼び出さずにスクリプトを表示
    --episode N  指定エピソードのみ処理
    --limit N    生成数を制限

必要な環境変数:
    GOOGLE_CLOUD_PROJECT  - GCPプロジェクトID
    GOOGLE_APPLICATION_CREDENTIALS - サービスアカウントキーのパス

出力:
    outputs/audio/episode{N}/scene_{id}_{index}.mp3
"""

import argparse
import json
import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional

# Google Cloud Text-to-Speech をインポート
try:
    from google.cloud import texttospeech
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    print("警告: google-cloud-texttospeech がインストールされていません")
    print("      pip install google-cloud-texttospeech")


def load_json(filepath: Path) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """JSONファイルを保存"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_script_hash(text: str, voice_settings: dict) -> str:
    """スクリプトのハッシュを計算（キャッシュ用）"""
    content = f"{text}|{json.dumps(voice_settings, sort_keys=True)}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def generate_audio_tts(
    text: str,
    voice_settings: dict,
    output_path: Path,
) -> bool:
    """Google TTS APIで音声を生成"""
    if not TTS_AVAILABLE:
        print("  エラー: TTS SDKが利用できません")
        return False

    try:
        client = texttospeech.TextToSpeechClient()

        # 入力テキスト
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # 音声設定
        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_settings.get("language", "ja-JP"),
            name=voice_settings.get("name", "ja-JP-Neural2-B"),
        )

        # オーディオ設定
        pitch = voice_settings.get("pitch", 0)
        speaking_rate = voice_settings.get("speaking_rate", 1.0)

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            pitch=pitch,
            speaking_rate=speaking_rate,
        )

        # 音声合成
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        # 保存
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        return True

    except Exception as e:
        print(f"  エラー: {e}")
        return False


def process_episode(
    scripts_path: Path,
    output_dir: Path,
    manifest_path: Path,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> tuple[int, int, int]:
    """1つのエピソードの音声を生成"""

    data = load_json(scripts_path)
    episode_num = data.get("episode", 1)
    scripts = data.get("scripts", [])

    # マニフェスト読み込み
    manifest = {}
    if manifest_path.exists():
        manifest = load_json(manifest_path)

    episode_output_dir = output_dir / f"episode{episode_num}"
    episode_output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    failed = 0

    for i, script_data in enumerate(scripts):
        if limit and generated >= limit:
            break

        scene_id = script_data.get("scene_id", "unknown")
        beat_index = script_data.get("beat_index", 0)
        text = script_data.get("text", "")
        voice_settings = script_data.get("voice_settings", {})

        if not text:
            continue

        # 出力ファイル名
        filename = f"{scene_id}_{beat_index:03d}.mp3"
        output_path = episode_output_dir / filename

        # ハッシュでキャッシュ確認
        script_hash = compute_script_hash(text, voice_settings)
        manifest_key = f"ep{episode_num}_{scene_id}_{beat_index}"

        if manifest_key in manifest:
            existing = manifest[manifest_key]
            if existing.get("script_hash") == script_hash and output_path.exists():
                skipped += 1
                continue

        speaker = script_data.get("speaker", "narrator")
        print(f"  [{i+1}/{len(scripts)}] {filename} ({speaker})")

        if dry_run:
            print(f"    テキスト: {text[:50]}...")
            print(f"    音声: {voice_settings.get('name', 'default')}")
            generated += 1
            continue

        # 音声生成
        success = generate_audio_tts(
            text=text,
            voice_settings=voice_settings,
            output_path=output_path,
        )

        if success:
            generated += 1
            # マニフェスト更新
            manifest[manifest_key] = {
                "path": str(output_path.relative_to(output_dir.parent)),
                "script_hash": script_hash,
                "scene_id": scene_id,
                "beat_index": beat_index,
                "speaker": speaker,
                "duration_estimate": len(text) * 0.15,  # 概算
            }
            save_json(manifest_path, manifest)
        else:
            failed += 1

        # レート制限対策
        time.sleep(0.1)

    return generated, skipped, failed


def main():
    parser = argparse.ArgumentParser(description="Google TTSで音声を生成")
    parser.add_argument("--dry-run", action="store_true", help="APIを呼び出さずに確認")
    parser.add_argument("--episode", type=int, help="指定エピソードのみ処理")
    parser.add_argument("--limit", type=int, help="生成数の上限")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    scripts_dir = base_dir / "prompts" / "tts"
    output_dir = base_dir / "outputs" / "audio"
    manifest_path = output_dir / "manifest.json"

    # GCP設定確認
    if not args.dry_run:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            print("エラー: GOOGLE_CLOUD_PROJECT 環境変数を設定してください")
            print()
            print("例:")
            print("  export GOOGLE_CLOUD_PROJECT=your-project-id")
            print("  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json")
            sys.exit(1)

        if not TTS_AVAILABLE:
            print("エラー: TTS SDKをインストールしてください")
            print("  pip install google-cloud-texttospeech")
            sys.exit(1)

        print(f"GCPプロジェクト: {project_id}")

    print()
    print("音声生成を開始します...")
    if args.dry_run:
        print("(ドライラン: APIは呼び出しません)")
    print()

    total_generated = 0
    total_skipped = 0
    total_failed = 0

    # エピソード処理
    for episode_num in range(1, 5):
        if args.episode and episode_num != args.episode:
            continue

        scripts_path = scripts_dir / f"episode{episode_num}_scripts.json"
        if not scripts_path.exists():
            print(f"エピソード{episode_num}: スクリプトファイルなし、スキップ")
            continue

        print(f"エピソード{episode_num}:")

        generated, skipped, failed = process_episode(
            scripts_path=scripts_path,
            output_dir=output_dir,
            manifest_path=manifest_path,
            dry_run=args.dry_run,
            limit=args.limit,
        )

        total_generated += generated
        total_skipped += skipped
        total_failed += failed

        print(f"  完了: 生成={generated}, スキップ={skipped}, 失敗={failed}")
        print()

    print("=" * 50)
    print(f"合計: 生成={total_generated}, スキップ={total_skipped}, 失敗={total_failed}")
    print()
    print(f"出力ディレクトリ: {output_dir}")
    print(f"マニフェスト: {manifest_path}")


if __name__ == "__main__":
    main()
