#!/usr/bin/env python3
"""
generate_prompts.py - シーンデータからAPI用プロンプトを生成

使用方法:
    python scripts/generate_prompts.py

入力:
    data/scenes/episode*.json
    data/characters.json
    data/locations.json

出力:
    prompts/imagen/episode{N}_prompts.json
    prompts/tts/episode{N}_scripts.json
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImagePrompt:
    """画像生成用プロンプト"""
    scene_id: str
    beat_index: int
    prompt: str
    negative_prompt: str
    style: str
    characters: list
    location: str
    weather: Optional[str]
    time: Optional[str]

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "beat_index": self.beat_index,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "style": self.style,
            "characters": self.characters,
            "location": self.location,
            "weather": self.weather,
            "time": self.time,
        }


@dataclass
class TTSScript:
    """TTS用スクリプト"""
    scene_id: str
    beat_index: int
    speaker: Optional[str]
    text: str
    emotion: Optional[str]
    voice_settings: dict

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "beat_index": self.beat_index,
            "speaker": self.speaker,
            "text": self.text,
            "emotion": self.emotion,
            "voice_settings": self.voice_settings,
        }


def load_json(filepath: Path) -> dict:
    """JSONファイルを読み込む"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_weather_description(weather: Optional[str]) -> str:
    """天候を英語の説明に変換"""
    weather_map = {
        "rain": "rainy night, wet surfaces, rain drops",
        "rain_heavy": "heavy rain, stormy, water puddles",
        "rain_light": "light rain, drizzle, misty",
        "thunderstorm": "thunderstorm, lightning, dramatic sky",
        "moonlight": "moonlit night, silver light, clear sky",
        "clear": "clear weather, bright",
        "clearing": "clouds parting, rainbow visible",
        "dawn": "pre-dawn, purple sky, first light",
        "sunrise": "sunrise, orange sky, morning light",
    }
    return weather_map.get(weather, "night time")


def get_time_description(time: Optional[str]) -> str:
    """時刻を英語の説明に変換"""
    if not time:
        return "late night"

    hour = int(time.split(":")[0])
    if hour < 4:
        return "late night, deep darkness"
    elif hour < 6:
        return "pre-dawn, dark with hints of light"
    elif hour < 8:
        return "early morning, soft light"
    else:
        return "daytime"


def generate_image_prompt(
    scene: dict,
    beat: dict,
    beat_index: int,
    characters_data: dict,
    locations_data: dict,
) -> Optional[ImagePrompt]:
    """ビートから画像生成プロンプトを生成"""

    # ナレーションビートのみ画像生成対象
    if beat.get("type") != "narration":
        return None

    # 短すぎるナレーションはスキップ
    if len(beat.get("text", "")) < 20:
        return None

    scene_id = scene.get("id", "unknown")
    location_id = scene.get("location", "lost_and_found")
    weather = scene.get("weather")
    time = scene.get("time")
    chars_present = scene.get("characters_present", [])

    # ロケーション情報を取得
    location_info = locations_data.get("locations", {}).get(location_id, {})
    location_prompt = location_info.get("imagen_prompt", {})
    location_base = location_prompt.get("base", "Japanese interior scene")
    location_style = location_prompt.get("style", "anime style")
    location_negative = location_prompt.get("negative", "")

    # キャラクター情報を収集
    char_prompts = []
    for char_id in chars_present[:2]:  # 最大2キャラまで
        char_info = characters_data.get("characters", {}).get(char_id, {})
        char_imagen = char_info.get("imagen_prompt", {})
        if char_imagen.get("base"):
            char_prompts.append(char_imagen.get("base"))

    # 天候・時刻の説明
    weather_desc = get_weather_description(weather)
    time_desc = get_time_description(time)

    # ビートのテキストからシーン説明を抽出
    beat_text = beat.get("text", "")

    # プロンプト組み立て
    prompt_parts = [
        location_base,
        weather_desc,
        time_desc,
    ]

    if char_prompts:
        prompt_parts.append(", ".join(char_prompts))

    # シーン固有の要素を追加
    if "雨" in beat_text:
        prompt_parts.append("rain falling")
    if "窓" in beat_text:
        prompt_parts.append("looking through window")
    if "立っ" in beat_text:
        prompt_parts.append("standing figure")
    if "座っ" in beat_text:
        prompt_parts.append("sitting figure")

    prompt = ", ".join(prompt_parts)

    # ネガティブプロンプト
    negative_parts = [
        location_negative,
        "low quality, blurry, distorted faces, extra limbs",
    ]
    negative_prompt = ", ".join(filter(None, negative_parts))

    return ImagePrompt(
        scene_id=scene_id,
        beat_index=beat_index,
        prompt=prompt,
        negative_prompt=negative_prompt,
        style=location_style,
        characters=chars_present,
        location=location_id,
        weather=weather,
        time=time,
    )


def generate_tts_script(
    scene: dict,
    beat: dict,
    beat_index: int,
    characters_data: dict,
) -> Optional[TTSScript]:
    """ビートからTTSスクリプトを生成"""

    beat_type = beat.get("type")
    text = beat.get("text", "")

    if not text:
        return None

    scene_id = scene.get("id", "unknown")
    speaker = beat.get("speaker")
    emotion = beat.get("emotion")

    # 音声設定を取得
    voice_settings = {}

    if speaker:
        char_info = characters_data.get("characters", {}).get(speaker, {})
        voice_info = char_info.get("voice", {})
        voice_settings = {
            "language": voice_info.get("language", "ja-JP"),
            "name": voice_info.get("name", "ja-JP-Neural2-B"),
            "pitch": voice_info.get("pitch", 0),
            "speaking_rate": voice_info.get("speaking_rate", 1.0),
        }
    else:
        # ナレーション用のデフォルト設定
        voice_settings = {
            "language": "ja-JP",
            "name": "ja-JP-Neural2-C",  # 落ち着いた声
            "pitch": -1,
            "speaking_rate": 0.95,
        }

    # 感情に基づいて音声パラメータを調整
    if emotion:
        emotion_adjustments = {
            "excited": {"pitch": 2, "speaking_rate": 1.1},
            "sad": {"pitch": -2, "speaking_rate": 0.9},
            "angry": {"pitch": 1, "speaking_rate": 1.05},
            "nervous": {"pitch": 1, "speaking_rate": 1.1},
            "calm": {"pitch": -1, "speaking_rate": 0.95},
            "surprised": {"pitch": 3, "speaking_rate": 1.15},
            "tearful": {"pitch": -1, "speaking_rate": 0.85},
        }
        adj = emotion_adjustments.get(emotion, {})
        if adj:
            voice_settings["pitch"] = voice_settings.get("pitch", 0) + adj.get("pitch", 0)
            voice_settings["speaking_rate"] = voice_settings.get("speaking_rate", 1.0) * adj.get("speaking_rate", 1.0)

    return TTSScript(
        scene_id=scene_id,
        beat_index=beat_index,
        speaker=speaker,
        text=text,
        emotion=emotion,
        voice_settings=voice_settings,
    )


def process_episode(
    episode_path: Path,
    characters_data: dict,
    locations_data: dict,
    output_dir: Path,
) -> tuple[int, int]:
    """1つのエピソードを処理"""

    episode_data = load_json(episode_path)
    episode_num = episode_data.get("episode", 1)

    image_prompts = []
    tts_scripts = []

    for scene in episode_data.get("scenes", []):
        for beat_index, beat in enumerate(scene.get("beats", [])):
            # 画像プロンプト生成
            img_prompt = generate_image_prompt(
                scene, beat, beat_index, characters_data, locations_data
            )
            if img_prompt:
                image_prompts.append(img_prompt.to_dict())

            # TTSスクリプト生成
            tts_script = generate_tts_script(
                scene, beat, beat_index, characters_data
            )
            if tts_script:
                tts_scripts.append(tts_script.to_dict())

    # 画像プロンプト出力
    imagen_dir = output_dir / "imagen"
    imagen_dir.mkdir(parents=True, exist_ok=True)
    imagen_path = imagen_dir / f"episode{episode_num}_prompts.json"
    with open(imagen_path, "w", encoding="utf-8") as f:
        json.dump({
            "episode": episode_num,
            "prompts": image_prompts,
        }, f, ensure_ascii=False, indent=2)

    # TTSスクリプト出力
    tts_dir = output_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    tts_path = tts_dir / f"episode{episode_num}_scripts.json"
    with open(tts_path, "w", encoding="utf-8") as f:
        json.dump({
            "episode": episode_num,
            "scripts": tts_scripts,
        }, f, ensure_ascii=False, indent=2)

    return len(image_prompts), len(tts_scripts)


def main():
    """メイン処理"""
    base_dir = Path(__file__).parent.parent
    scenes_dir = base_dir / "data" / "scenes"
    output_dir = base_dir / "prompts"

    # キャラクター・ロケーションデータを読み込み
    characters_data = load_json(base_dir / "data" / "characters.json")
    locations_data = load_json(base_dir / "data" / "locations.json")

    print("シーンデータからプロンプトを生成中...")
    print()

    total_images = 0
    total_tts = 0

    # 手動作成したシーンファイルを優先、なければ自動抽出版を使用
    for i in range(1, 5):
        manual_path = scenes_dir / f"episode{i}.json"
        extracted_path = scenes_dir / f"episode{i}_extracted.json"

        if manual_path.exists():
            episode_path = manual_path
            source = "手動"
        elif extracted_path.exists():
            episode_path = extracted_path
            source = "自動抽出"
        else:
            print(f"  エピソード{i}: ファイルなし、スキップ")
            continue

        img_count, tts_count = process_episode(
            episode_path, characters_data, locations_data, output_dir
        )
        total_images += img_count
        total_tts += tts_count

        print(f"  エピソード{i} ({source})")
        print(f"    画像プロンプト: {img_count}")
        print(f"    TTSスクリプト: {tts_count}")

    print()
    print(f"合計:")
    print(f"  画像プロンプト: {total_images}")
    print(f"  TTSスクリプト: {total_tts}")
    print()
    print("出力ディレクトリ:")
    print(f"  prompts/imagen/  - 画像生成用プロンプト")
    print(f"  prompts/tts/     - TTS用スクリプト")


if __name__ == "__main__":
    main()
