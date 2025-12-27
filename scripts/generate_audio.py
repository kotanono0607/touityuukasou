#!/usr/bin/env python3
"""
generate_audio.py - Gemini TTS APIを使用して音声を生成

使用方法:
    python scripts/generate_audio.py [--dry-run] [--episode N] [--limit N]

オプション:
    --dry-run    APIを呼び出さずにスクリプトを表示
    --episode N  指定エピソードのみ処理
    --limit N    生成数を制限

必要な環境変数:
    GEMINI_API_KEY - Gemini APIキー

出力:
    outputs/audio/episode{N}/scene_{id}_{index}.wav
"""

import argparse
import json
import os
import sys
import time
import hashlib
import wave
from pathlib import Path
from typing import Optional

# Gemini APIをインポート
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("警告: google-genai がインストールされていません")
    print("      pip install google-genai")

# 設定
GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
WAIT_BETWEEN_AUDIO = 2
MAX_RETRIES = 3
RETRY_WAIT = 30

# キャラクター別の音声設定
# 利用可能な音声: Aoede, Charon, Fenrir, Kore, Puck, etc.
CHARACTER_VOICES = {
    "ren": {"voice": "Orus", "style": "疲れた感じで少し投げやりに"},
    "yuki": {"voice": "Kore", "style": "明るく元気にハキハキと"},
    "sumika": {"voice": "Aoede", "style": "感情を抑えながらも切なく"},
    "sumika_young": {"voice": "Kore", "style": "夢を追う情熱を込めて"},
    "mother": {"voice": "Aoede", "style": "優しく穏やかに"},
    "mother_young": {"voice": "Aoede", "style": "厳しくも愛情を込めて"},
    "father": {"voice": "Charon", "style": "温かく"},
    "voice_entity": {"voice": "Fenrir", "style": "不気味に歪んだ感じで"},
    "narrator": {"voice": "Puck", "style": "落ち着いて淡々と"},
}


def load_json(filepath: Path) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """JSONファイルを保存"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_script_hash(text: str, speaker: str) -> str:
    """スクリプトのハッシュを計算（キャッシュ用）"""
    content = f"{text}|{speaker}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def save_pcm_as_wav(pcm_data: bytes, output_path: Path):
    """PCMデータをWAVファイルとして保存（24kHz, 16bit, mono）"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)        # モノラル
        wf.setsampwidth(2)        # 16bit = 2bytes
        wf.setframerate(24000)    # 24kHz
        wf.writeframes(pcm_data)


def generate_audio_gemini(
    client,
    text: str,
    speaker: str,
    emotion: str,
    output_path: Path,
) -> bool:
    """Gemini TTS APIで音声を生成（リトライ機能付き）"""

    # キャラクターの音声設定を取得
    voice_config = CHARACTER_VOICES.get(speaker, CHARACTER_VOICES["narrator"])
    voice_name = voice_config["voice"]
    style = voice_config["style"]

    # 感情を含めたプロンプト
    emotion_note = f"（{emotion}）" if emotion else ""
    prompt = f"{style}{emotion_note}読んでください: {text}"

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        )
                    ),
                )
            )

            # レスポンスから音声データを抽出してWAVとして保存
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    save_pcm_as_wav(part.inline_data.data, output_path)
                    return True

            print("  警告: 音声が生成されませんでした")
            return False

        except Exception as e:
            error_msg = str(e)
            print(f"  試行 {attempt + 1}/{MAX_RETRIES} 失敗: {error_msg}")

            if "429" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
                print(f"  レート制限検知。{RETRY_WAIT}秒待機中...")
                time.sleep(RETRY_WAIT)
            elif attempt < MAX_RETRIES - 1:
                print(f"  {RETRY_WAIT}秒後にリトライ...")
                time.sleep(RETRY_WAIT)
            else:
                return False

    return False


def process_episode(
    client,
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
        speaker = script_data.get("speaker", "narrator")
        emotion = script_data.get("emotion", "")

        if not text:
            continue

        filename = f"{scene_id}_{beat_index:03d}.wav"
        output_path = episode_output_dir / filename

        script_hash = compute_script_hash(text, speaker)
        manifest_key = f"ep{episode_num}_{scene_id}_{beat_index}"

        if manifest_key in manifest:
            existing = manifest[manifest_key]
            if existing.get("script_hash") == script_hash and output_path.exists():
                skipped += 1
                continue

        voice_name = CHARACTER_VOICES.get(speaker, CHARACTER_VOICES["narrator"])["voice"]
        print(f"  [{i+1}/{len(scripts)}] {filename} ({speaker} -> {voice_name})")

        if dry_run:
            print(f"    テキスト: {text[:50]}...")
            generated += 1
            continue

        success = generate_audio_gemini(
            client=client,
            text=text,
            speaker=speaker,
            emotion=emotion,
            output_path=output_path,
        )

        if success:
            generated += 1
            manifest[manifest_key] = {
                "path": str(output_path.relative_to(output_dir.parent)),
                "script_hash": script_hash,
                "scene_id": scene_id,
                "beat_index": beat_index,
                "speaker": speaker,
                "voice": voice_name,
            }
            save_json(manifest_path, manifest)
            print(f"    保存完了: {output_path}")
        else:
            failed += 1

        if i < len(scripts) - 1 and not dry_run:
            print(f"    {WAIT_BETWEEN_AUDIO}秒待機中...")
            time.sleep(WAIT_BETWEEN_AUDIO)

    return generated, skipped, failed


def main():
    parser = argparse.ArgumentParser(description="Gemini TTS APIで音声を生成")
    parser.add_argument("--dry-run", action="store_true", help="APIを呼び出さずに確認")
    parser.add_argument("--episode", type=int, help="指定エピソードのみ処理")
    parser.add_argument("--limit", type=int, help="生成数の上限")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    scripts_dir = base_dir / "prompts" / "tts"
    output_dir = base_dir / "outputs" / "audio"
    manifest_path = output_dir / "manifest.json"

    client = None

    if not args.dry_run:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("エラー: GEMINI_API_KEY 環境変数を設定してください")
            print()
            print("例:")
            print("  export GEMINI_API_KEY=your-api-key")
            sys.exit(1)

        if not GENAI_AVAILABLE:
            print("エラー: google-genai をインストールしてください")
            print("  pip install google-genai")
            sys.exit(1)

        client = genai.Client(api_key=api_key)
        print("Gemini API クライアント初期化完了")

    print()
    print("音声生成を開始します...")
    if args.dry_run:
        print("(ドライラン: APIは呼び出しません)")
    print()

    total_generated = 0
    total_skipped = 0
    total_failed = 0

    for episode_num in range(1, 5):
        if args.episode and episode_num != args.episode:
            continue

        scripts_path = scripts_dir / f"episode{episode_num}_scripts.json"
        if not scripts_path.exists():
            print(f"エピソード{episode_num}: スクリプトファイルなし、スキップ")
            continue

        print(f"エピソード{episode_num}:")

        generated, skipped, failed = process_episode(
            client=client,
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


if __name__ == "__main__":
    main()
