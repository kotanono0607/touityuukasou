#!/usr/bin/env python3
"""
generate_images.py - Gemini APIを使用して画像を生成

使用方法:
    python scripts/generate_images.py [--dry-run] [--episode N] [--limit N]

オプション:
    --dry-run    APIを呼び出さずにプロンプトを表示
    --episode N  指定エピソードのみ処理
    --limit N    生成枚数を制限

必要な環境変数:
    GEMINI_API_KEY - Gemini APIキー

出力:
    outputs/images/episode{N}/scene_{id}_{index}.png
"""

import argparse
import json
import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional, List

# Gemini APIをインポート
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("警告: google-genai がインストールされていません")
    print("      pip install google-genai")

# PIL（画像読み込み用）
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("警告: Pillow がインストールされていません（参照画像機能に必要）")
    print("      pip install Pillow")

# 設定
GEMINI_MODEL = "gemini-2.5-flash-image"  # 画像生成対応モデル（旧称: ナノバナナプロ）
WAIT_BETWEEN_IMAGES = 10  # 画像間の待機秒数（レート制限対策）
MAX_RETRIES = 3  # 最大リトライ回数
RETRY_WAIT = 30  # リトライ時の待機秒数


def load_json(filepath: Path) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """JSONファイルを保存"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_prompt_hash(prompt: str, negative_prompt: str, ref_images: List[str] = None) -> str:
    """プロンプトのハッシュを計算（キャッシュ用）"""
    ref_str = ",".join(sorted(ref_images)) if ref_images else ""
    content = f"{prompt}|{negative_prompt}|{ref_str}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def load_reference_image(image_path: Path, debug: bool = False) -> Optional[Image.Image]:
    """参照画像を読み込む"""
    if not PIL_AVAILABLE:
        if debug:
            print(f"    [DEBUG] PIL not available")
        return None
    if not image_path.exists():
        if debug:
            print(f"    [DEBUG] Image not found: {image_path}")
        return None
    try:
        img = Image.open(image_path)
        # 大きすぎる画像はリサイズ（API制限対策）
        max_size = 1024
        if img.width > max_size or img.height > max_size:
            ratio = min(max_size / img.width, max_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        return img
    except Exception as e:
        print(f"  警告: 参照画像読み込み失敗 {image_path}: {e}")
        return None


def get_reference_images(
    prompt_data: dict,
    characters_data: dict,
    locations_data: dict,
    base_dir: Path,
    debug: bool = False,
) -> List[tuple[str, Image.Image]]:
    """プロンプトに対応する参照画像を取得"""
    ref_images = []

    # キャラクター参照画像
    characters = prompt_data.get("characters", [])
    if debug:
        print(f"    [DEBUG] Characters in prompt: {characters}")
    for char_id in characters[:2]:  # 最大2キャラまで
        char_info = characters_data.get("characters", {}).get(char_id, {})
        ref_path = char_info.get("reference_image")
        if debug:
            print(f"    [DEBUG] {char_id} -> ref_path: {ref_path}")
        if ref_path:
            img = load_reference_image(base_dir / ref_path, debug)
            if img:
                char_name = char_info.get("name", char_id)
                ref_images.append((f"Character: {char_name}", img))

    # 背景参照画像
    location_id = prompt_data.get("location", "")
    if debug:
        print(f"    [DEBUG] Location: {location_id}")
    location_info = locations_data.get("locations", {}).get(location_id, {})

    # 複数の参照画像がある場合（天候/時間帯で選択）
    ref_images_dict = location_info.get("reference_images", {})
    weather = prompt_data.get("weather", "")
    if debug:
        print(f"    [DEBUG] Location ref_images_dict: {ref_images_dict}")

    if ref_images_dict:
        # 天候に応じた画像を選択
        if "rain" in weather and "night_rain" in ref_images_dict:
            ref_path = ref_images_dict["night_rain"]
        elif "morning" in ref_images_dict:
            ref_path = ref_images_dict.get("morning")
        else:
            # 最初の画像を使用
            ref_path = list(ref_images_dict.values())[0] if ref_images_dict else None
    else:
        # 単一の参照画像
        ref_path = location_info.get("reference_image")

    if ref_path:
        if debug:
            print(f"    [DEBUG] Background ref_path: {ref_path}")
        img = load_reference_image(base_dir / ref_path, debug)
        if img:
            loc_name = location_info.get("name", location_id)
            ref_images.append((f"Background: {loc_name}", img))

    if debug:
        print(f"    [DEBUG] Total ref_images loaded: {len(ref_images)}")
    return ref_images


def build_character_descriptions(
    character_ids: List[str],
    characters_data: dict,
) -> str:
    """キャラクターIDリストから統一された説明文を生成"""
    descriptions = []
    characters = characters_data.get("characters", {})

    for char_id in character_ids:
        char_info = characters.get(char_id, {})
        if not char_info:
            continue

        # imagen_prompt.base を優先使用、なければ appearance から生成
        imagen_prompt = char_info.get("imagen_prompt", {})
        if imagen_prompt.get("base"):
            desc = imagen_prompt["base"]
        else:
            # appearance から説明を構築
            appearance = char_info.get("appearance", {})
            parts = []
            if char_info.get("gender"):
                gender_map = {"male": "male", "female": "female"}
                parts.append(gender_map.get(char_info["gender"], "person"))
            if char_info.get("age"):
                parts.append(f"{char_info['age']} years old")
            if appearance.get("hair"):
                parts.append(f"{appearance['hair']} hair")
            if appearance.get("eyes"):
                parts.append(f"{appearance['eyes']} eyes")
            if appearance.get("build"):
                parts.append(appearance["build"])
            if appearance.get("clothing"):
                parts.append(appearance["clothing"])
            if appearance.get("features"):
                parts.extend(appearance["features"])
            desc = ", ".join(parts) if parts else char_info.get("description", "")

        name = char_info.get("name_en", char_info.get("name", char_id))
        descriptions.append(f"{name}: {desc}")

    return "\n".join(descriptions)


def build_gemini_prompt(
    prompt: str,
    negative_prompt: str,
    style: str = "",
    character_descriptions: str = "",
) -> str:
    """Gemini用のプロンプトを構築（参考コード形式）"""

    # キャラクター説明セクション
    char_section = ""
    if character_descriptions:
        char_section = f"""
CHARACTERS (maintain exact visual consistency across all scenes):
{character_descriptions}
"""

    full_prompt = f"""Generate a single high-quality anime illustration.

CRITICAL RULES:
- NO speech bubbles, NO text, NO words, NO letters anywhere
- Fully rendered detailed background (NOT white/blank background)
- Rich colors and shading
- Professional anime art quality

QUALITY: High detail, vibrant colors, fully colored illustration, detailed background art, professional anime production quality, 4K resolution

STYLE: Japanese anime/manga style, clean bold lineart, expressive faces, aspect ratio 16:9
{style}
{char_section}
SCENE DESCRIPTION:
{prompt}

AVOID: {negative_prompt}
"""
    return full_prompt


def generate_image_gemini(
    client,
    prompt: str,
    negative_prompt: str,
    style: str,
    output_path: Path,
    character_descriptions: str = "",
) -> bool:
    """Gemini APIで画像を生成（リトライ機能付き）"""
    full_prompt = build_gemini_prompt(
        prompt, negative_prompt, style, character_descriptions
    )

    # コンテンツ構築（テキストプロンプトのみ）
    contents = full_prompt

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

            # レスポンスから画像データを抽出
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    # 画像を保存
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(part.inline_data.data)
                    return True

            print("  警告: 画像が生成されませんでした")
            return False

        except Exception as e:
            error_msg = str(e)
            print(f"  試行 {attempt + 1}/{MAX_RETRIES} 失敗: {error_msg}")

            # レート制限エラーの場合は長めに待機
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
    prompts_path: Path,
    output_dir: Path,
    manifest_path: Path,
    characters_data: dict,
    locations_data: dict,
    base_dir: Path,
    dry_run: bool = False,
    limit: Optional[int] = None,
    debug: bool = False,
) -> tuple[int, int, int]:
    """1つのエピソードの画像を生成"""

    data = load_json(prompts_path)
    episode_num = data.get("episode", 1)
    prompts = data.get("prompts", [])

    # マニフェスト読み込み（既存の生成結果を確認）
    manifest = {}
    if manifest_path.exists():
        manifest = load_json(manifest_path)

    episode_output_dir = output_dir / f"episode{episode_num}"
    episode_output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    failed = 0

    for i, prompt_data in enumerate(prompts):
        if limit and generated >= limit:
            break

        scene_id = prompt_data.get("scene_id", "unknown")
        beat_index = prompt_data.get("beat_index", 0)
        prompt = prompt_data.get("prompt", "")
        negative_prompt = prompt_data.get("negative_prompt", "")
        style = prompt_data.get("style", "")

        # 出力ファイル名
        filename = f"{scene_id}_{beat_index:03d}.png"
        output_path = episode_output_dir / filename

        # キャラクター説明を生成（テキストベース）
        character_ids = prompt_data.get("characters", [])
        char_descriptions = build_character_descriptions(character_ids, characters_data)

        if debug and char_descriptions:
            print(f"    [DEBUG] Characters: {character_ids}")

        # ハッシュでキャッシュ確認（キャラクター説明も含める）
        prompt_hash = compute_prompt_hash(prompt, negative_prompt, character_ids)
        manifest_key = f"ep{episode_num}_{scene_id}_{beat_index}"

        if manifest_key in manifest:
            existing = manifest[manifest_key]
            if existing.get("prompt_hash") == prompt_hash and output_path.exists():
                print(f"  [{i+1}/{len(prompts)}] {filename} - スキップ（キャッシュ）")
                skipped += 1
                continue

        char_info = f" (キャラ: {len(character_ids)}人)" if character_ids else ""
        print(f"  [{i+1}/{len(prompts)}] {filename}{char_info}")

        if dry_run:
            print(f"    プロンプト: {prompt[:80]}...")
            print(f"    ネガティブ: {negative_prompt[:50]}...")
            if char_descriptions:
                print(f"    キャラクター説明:")
                for line in char_descriptions.split("\n"):
                    print(f"      {line[:70]}...")
            generated += 1
            continue

        # 画像生成
        success = generate_image_gemini(
            client=client,
            prompt=prompt,
            negative_prompt=negative_prompt,
            style=style,
            output_path=output_path,
            character_descriptions=char_descriptions,
        )

        if success:
            generated += 1
            # マニフェスト更新
            manifest[manifest_key] = {
                "path": str(output_path.relative_to(output_dir.parent)),
                "prompt_hash": prompt_hash,
                "scene_id": scene_id,
                "beat_index": beat_index,
            }
            save_json(manifest_path, manifest)
            print(f"    保存完了: {output_path}")
        else:
            failed += 1

        # レート制限対策
        if i < len(prompts) - 1:
            print(f"    {WAIT_BETWEEN_IMAGES}秒待機中...")
            time.sleep(WAIT_BETWEEN_IMAGES)

    return generated, skipped, failed


def main():
    parser = argparse.ArgumentParser(description="Gemini APIで画像を生成")
    parser.add_argument("--dry-run", action="store_true", help="APIを呼び出さずに確認")
    parser.add_argument("--episode", type=int, help="指定エピソードのみ処理")
    parser.add_argument("--limit", type=int, help="生成枚数の上限")
    parser.add_argument("--debug", action="store_true", help="デバッグ出力を表示")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    prompts_dir = base_dir / "prompts" / "imagen"
    output_dir = base_dir / "outputs" / "images"
    manifest_path = output_dir / "manifest.json"

    # キャラクター・ロケーションデータを読み込み
    characters_data = load_json(base_dir / "data" / "characters.json")
    locations_data = load_json(base_dir / "data" / "locations.json")

    client = None

    # APIキー確認
    if not args.dry_run:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("エラー: GEMINI_API_KEY 環境変数を設定してください")
            print()
            print("例:")
            print("  export GEMINI_API_KEY=your-api-key")
            print()
            print("または:")
            print("  GEMINI_API_KEY=your-api-key python scripts/generate_images.py")
            sys.exit(1)

        if not GENAI_AVAILABLE:
            print("エラー: google-genai をインストールしてください")
            print("  pip install google-genai")
            sys.exit(1)

        # クライアント初期化
        client = genai.Client(api_key=api_key)
        print("Gemini API クライアント初期化完了")

    print()
    print("画像生成を開始します...")
    print("(テキストベースキャラクター記述モード: imagen_prompt.baseを使用)")
    if args.dry_run:
        print("(ドライラン: APIは呼び出しません)")
    if args.debug:
        print(f"[DEBUG] base_dir: {base_dir}")
    print()

    total_generated = 0
    total_skipped = 0
    total_failed = 0

    # エピソード処理
    for episode_num in range(1, 5):
        if args.episode and episode_num != args.episode:
            continue

        prompts_path = prompts_dir / f"episode{episode_num}_prompts.json"
        if not prompts_path.exists():
            print(f"エピソード{episode_num}: プロンプトファイルなし、スキップ")
            continue

        print(f"エピソード{episode_num}:")

        generated, skipped, failed = process_episode(
            client=client,
            prompts_path=prompts_path,
            output_dir=output_dir,
            manifest_path=manifest_path,
            characters_data=characters_data,
            locations_data=locations_data,
            base_dir=base_dir,
            dry_run=args.dry_run,
            limit=args.limit,
            debug=args.debug,
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
