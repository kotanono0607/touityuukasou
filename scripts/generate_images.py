#!/usr/bin/env python3
"""
generate_images.py - Imagen APIを使用して画像を生成

使用方法:
    python scripts/generate_images.py [--dry-run] [--episode N] [--limit N]

オプション:
    --dry-run    APIを呼び出さずにプロンプトを表示
    --episode N  指定エピソードのみ処理
    --limit N    生成枚数を制限

必要な環境変数:
    GOOGLE_CLOUD_PROJECT  - GCPプロジェクトID
    GOOGLE_APPLICATION_CREDENTIALS - サービスアカウントキーのパス

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
from typing import Optional

# Google Cloud AI Platform (Vertex AI) をインポート
try:
    from google.cloud import aiplatform
    from vertexai.preview.vision_models import ImageGenerationModel
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False
    print("警告: google-cloud-aiplatform がインストールされていません")
    print("      pip install google-cloud-aiplatform")


def load_json(filepath: Path) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """JSONファイルを保存"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_prompt_hash(prompt: str, negative_prompt: str) -> str:
    """プロンプトのハッシュを計算（キャッシュ用）"""
    content = f"{prompt}|{negative_prompt}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def generate_image_vertex_ai(
    prompt: str,
    negative_prompt: str,
    output_path: Path,
    model_name: str = "imagegeneration@006",
) -> bool:
    """Vertex AI Imagen APIで画像を生成"""
    if not VERTEX_AI_AVAILABLE:
        print("  エラー: Vertex AI SDKが利用できません")
        return False

    try:
        model = ImageGenerationModel.from_pretrained(model_name)

        response = model.generate_images(
            prompt=prompt,
            negative_prompt=negative_prompt,
            number_of_images=1,
            aspect_ratio="16:9",  # ワイドスクリーン
            safety_filter_level="block_few",
            person_generation="allow_adult",
        )

        if response.images:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            response.images[0].save(str(output_path))
            return True
        else:
            print("  警告: 画像が生成されませんでした")
            return False

    except Exception as e:
        print(f"  エラー: {e}")
        return False


def process_episode(
    prompts_path: Path,
    output_dir: Path,
    manifest_path: Path,
    dry_run: bool = False,
    limit: Optional[int] = None,
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

        # 出力ファイル名
        filename = f"{scene_id}_{beat_index:03d}.png"
        output_path = episode_output_dir / filename

        # ハッシュでキャッシュ確認
        prompt_hash = compute_prompt_hash(prompt, negative_prompt)
        manifest_key = f"ep{episode_num}_{scene_id}_{beat_index}"

        if manifest_key in manifest:
            existing = manifest[manifest_key]
            if existing.get("prompt_hash") == prompt_hash and output_path.exists():
                print(f"  [{i+1}/{len(prompts)}] {filename} - スキップ（キャッシュ）")
                skipped += 1
                continue

        print(f"  [{i+1}/{len(prompts)}] {filename}")

        if dry_run:
            print(f"    プロンプト: {prompt[:80]}...")
            print(f"    ネガティブ: {negative_prompt[:50]}...")
            generated += 1
            continue

        # 画像生成
        success = generate_image_vertex_ai(
            prompt=prompt,
            negative_prompt=negative_prompt,
            output_path=output_path,
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
        else:
            failed += 1

        # レート制限対策
        time.sleep(1)

    return generated, skipped, failed


def main():
    parser = argparse.ArgumentParser(description="Imagen APIで画像を生成")
    parser.add_argument("--dry-run", action="store_true", help="APIを呼び出さずに確認")
    parser.add_argument("--episode", type=int, help="指定エピソードのみ処理")
    parser.add_argument("--limit", type=int, help="生成枚数の上限")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    prompts_dir = base_dir / "prompts" / "imagen"
    output_dir = base_dir / "outputs" / "images"
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

        if VERTEX_AI_AVAILABLE:
            aiplatform.init(project=project_id, location="us-central1")
            print(f"GCPプロジェクト: {project_id}")
        else:
            print("エラー: Vertex AI SDKをインストールしてください")
            print("  pip install google-cloud-aiplatform")
            sys.exit(1)

    print()
    print("画像生成を開始します...")
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

        prompts_path = prompts_dir / f"episode{episode_num}_prompts.json"
        if not prompts_path.exists():
            print(f"エピソード{episode_num}: プロンプトファイルなし、スキップ")
            continue

        print(f"エピソード{episode_num}:")

        generated, skipped, failed = process_episode(
            prompts_path=prompts_path,
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
