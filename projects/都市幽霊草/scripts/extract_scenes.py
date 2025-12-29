#!/usr/bin/env python3
"""
extract_scenes.py - 小説Markdownファイルからシーンデータを抽出

使用方法:
    python scripts/extract_scenes.py

出力:
    data/scenes/episode{N}.json
"""

import json
import re
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Beat:
    """シーン内の1つのビート（セリフ、ナレーション等）"""
    type: str  # dialogue, narration, internal
    text: str
    speaker: Optional[str] = None
    emotion: Optional[str] = None
    action: Optional[str] = None
    voice_note: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"type": self.type, "text": self.text}
        if self.speaker:
            d["speaker"] = self.speaker
        if self.emotion:
            d["emotion"] = self.emotion
        if self.action:
            d["action"] = self.action
        if self.voice_note:
            d["voice_note"] = self.voice_note
        return d


@dataclass
class Scene:
    """1つのシーン"""
    id: str
    title: str
    location: str = "lost_and_found"
    time: Optional[str] = None
    weather: Optional[str] = None
    characters_present: list = field(default_factory=list)
    is_flashback: bool = False
    beats: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "location": self.location,
        }
        if self.time:
            d["time"] = self.time
        if self.weather:
            d["weather"] = self.weather
        d["characters_present"] = self.characters_present
        if self.is_flashback:
            d["is_flashback"] = True
        d["beats"] = [b.to_dict() for b in self.beats]
        return d


# キャラクター識別パターン
CHARACTER_PATTERNS = {
    "ren": [
        r"^レン",
        r"灰谷さん",
        r"俺",
        r"面倒だ",
    ],
    "yuki": [
        r"^ユキ",
        r"灰谷さん.*です",
        r"私も.*です",
    ],
    "sumika": [
        r"^澄香",
        r"蒼井さん",
        r"蒼井澄香",
    ],
    "mother": [
        r"^母",
        r"お母さん",
    ],
    "voice_entity": [
        r"怪異",
        r"黒い靄",
    ],
}

# 話者識別用のセリフパターン
SPEAKER_HINTS = {
    "灰谷さん": "yuki",  # ユキがレンを呼ぶ
    "蒼井さん": ["ren", "yuki"],  # レンかユキが澄香を呼ぶ
    "お母さん": "sumika",  # 澄香が母を呼ぶ
    "澄香": "mother",  # 母が澄香を呼ぶ
}

# ロケーション識別キーワード
LOCATION_KEYWORDS = {
    "遺失物取扱所": "lost_and_found",
    "窓口": "lost_and_found",
    "カウンター": "lost_and_found",
    "路地": "alley",
    "ライブハウス": "livehouse",
    "アパート": "sumika_apartment",
    "実家": "mother_house",
    "玄関": "mother_house_entrance",
    "駅前": "station_bench",
    "ベンチ": "station_bench",
}

# 天候識別キーワード
WEATHER_KEYWORDS = {
    "雨が降": "rain",
    "雨脚": "rain_heavy",
    "小降り": "rain_light",
    "雷": "thunderstorm",
    "稲光": "thunderstorm",
    "月明かり": "moonlight",
    "晴れ": "clear",
    "虹": "clearing",
    "夜明け": "dawn",
    "朝日": "sunrise",
}

# 時刻抽出パターン
TIME_PATTERNS = [
    r"(午前|午後)?(\d{1,2})時(\d{1,2})分",
    r"深夜零時(\d{1,2})分",
    r"深夜(\d{1,2})時",
]


def extract_time(text: str) -> Optional[str]:
    """テキストから時刻を抽出"""
    # 深夜零時パターン
    m = re.search(r"深夜零時(\d{1,2})分", text)
    if m:
        return f"00:{m.group(1).zfill(2)}"

    m = re.search(r"深夜(\d{1,2})時", text)
    if m:
        return f"{m.group(1).zfill(2)}:00"

    # 午前/午後パターン
    m = re.search(r"(午前|午後)?(\d{1,2})時(\d{1,2})分", text)
    if m:
        period, hour, minute = m.groups()
        hour = int(hour)
        if period == "午後" and hour < 12:
            hour += 12
        return f"{hour:02d}:{minute.zfill(2)}"

    return None


def detect_weather(text: str) -> Optional[str]:
    """テキストから天候を検出"""
    for keyword, weather in WEATHER_KEYWORDS.items():
        if keyword in text:
            return weather
    return None


def detect_location(text: str) -> str:
    """テキストからロケーションを検出"""
    for keyword, location in LOCATION_KEYWORDS.items():
        if keyword in text:
            return location
    return "lost_and_found"


def identify_speaker(line: str, context_lines: list, prev_speaker: Optional[str] = None) -> Optional[str]:
    """セリフの話者を識別"""

    # 最優先: セリフ内容から推測（呼びかけパターン）
    # ユキがレンを呼ぶ（「灰谷さん」を含むセリフは必ずユキ）
    if "灰谷さん" in line:
        return "yuki"

    # 直前の行に話者のヒントがあるか確認
    if context_lines:
        # 直近3行をチェック（新しい順）
        for prev_line in reversed(context_lines[-3:]):
            # 明確な話者指定パターン
            speech_verbs = ["言った", "呟", "尋ね", "答え", "続けた", "叫", "呼んだ", "口を開"]

            if ("レン" in prev_line or "灰谷が" in prev_line) and "灰谷さん" not in prev_line:
                if any(v in prev_line for v in speech_verbs):
                    return "ren"
            if "ユキ" in prev_line:
                if any(v in prev_line for v in speech_verbs) or "声が聞" in prev_line:
                    return "yuki"
            if ("澄香" in prev_line or ("女" in prev_line and "若い女" not in prev_line)) and "蒼井さん" not in prev_line:
                if any(v in prev_line for v in speech_verbs) or "声" in prev_line:
                    return "sumika"
            if "母" in prev_line and "お母さん" not in prev_line:
                if any(v in prev_line for v in speech_verbs) or "声" in prev_line:
                    return "mother"
            if "怪異" in prev_line or "靄" in prev_line:
                if any(v in prev_line for v in speech_verbs) or "声" in prev_line or "響" in prev_line:
                    return "voice_entity"

    # セリフ内容から推測（呼びかけパターン - 続き）
    # レンまたはユキが澄香を呼ぶ
    if "蒼井さん" in line:
        return "yuki" if prev_speaker == "ren" else "ren"
    # 澄香が母を呼ぶ
    if "お母さん" in line:
        return "sumika"
    # 母が澄香を呼ぶ（短い呼びかけ）
    if line.startswith("澄香") or (len(line) < 10 and "澄香" in line):
        return "mother"

    # レン特有の話し方
    if "面倒だ" in line:
        return "ren"
    if "俺" in line and "俺たち" not in line:
        return "ren"
    if line.startswith("……") and len(line) < 15:
        return "ren"
    if "だろ" in line and len(line) < 20:
        return "ren"

    # ユキ特有の話し方
    if line.endswith("ですか") or line.endswith("ますか"):
        return "yuki"
    if line.endswith("です！") or line.endswith("ます！"):
        return "yuki"
    if "私も" in line and "です" in line:
        return "yuki"

    # 澄香特有の話し方
    if "私" in line and "失く" in line:
        return "sumika"
    if "歌" in line and ("たい" in line or "えな" in line):
        return "sumika"

    # 怪異特有の話し方
    if "捨てた" in line or "待って" in line:
        if prev_speaker == "voice_entity" or "恨" in line:
            return "voice_entity"

    return prev_speaker


def parse_markdown(filepath: Path) -> tuple[str, str, list[Scene]]:
    """Markdownファイルをパースしてシーンリストを返す"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    # タイトル抽出
    title = ""
    title_en = ""
    for line in lines:
        if line.startswith("# "):
            m = re.search(r"「(.+)」", line)
            if m:
                title = m.group(1)
            break

    # エピソード番号抽出
    episode_num = 1
    m = re.search(r"第(\d+|一|二|三|四|最終)話", lines[0] if lines else "")
    if m:
        num_map = {"一": 1, "二": 2, "三": 3, "四": 4, "最終": 4}
        num = m.group(1)
        episode_num = num_map.get(num, int(num) if num.isdigit() else 1)

    scenes = []
    current_scene = None
    scene_count = 0
    current_beats = []
    context_lines = []
    prev_speaker = None
    is_flashback = False
    current_location = "lost_and_found"
    current_weather = None
    current_time = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # シーン区切り
        if line == "---":
            # 現在のシーンを保存
            if current_scene and current_beats:
                current_scene.beats = current_beats
                scenes.append(current_scene)

            # 次の数行をチェックして新しいシーンの情報を取得
            scene_count += 1
            preview_text = " ".join(lines[i+1:i+5]) if i+5 < len(lines) else ""

            # 回想シーンの検出
            is_flashback = "十年前" in preview_text or "回想" in preview_text

            # ロケーション検出
            new_location = detect_location(preview_text)
            if new_location != "lost_and_found":
                current_location = new_location

            # 天候検出
            new_weather = detect_weather(preview_text)
            if new_weather:
                current_weather = new_weather

            # 時刻検出
            new_time = extract_time(preview_text)
            if new_time:
                current_time = new_time

            # 新しいシーン作成
            current_scene = Scene(
                id=f"ep{episode_num}_sc{scene_count:03d}",
                title=f"シーン{scene_count}",
                location=current_location,
                time=current_time,
                weather=current_weather,
                is_flashback=is_flashback,
            )
            current_beats = []
            context_lines = []
            prev_speaker = None
            i += 1
            continue

        # 空行スキップ
        if not line:
            i += 1
            continue

        # タイトル行スキップ
        if line.startswith("#"):
            i += 1
            continue

        # 「了」行スキップ
        if "了" in line and len(line) < 20:
            i += 1
            continue

        # 引用ブロック（遺失物の詳細など）
        if line.startswith(">"):
            text = line.lstrip("> ").strip("『』")
            beat = Beat(type="narration", text=text)
            current_beats.append(beat)
            i += 1
            continue

        # セリフ検出（「」で囲まれている）
        if "「" in line and "」" in line:
            m = re.search(r"「(.+?)」", line)
            if m:
                dialogue_text = m.group(1)

                # 話者識別
                speaker = identify_speaker(dialogue_text, context_lines, prev_speaker)

                beat = Beat(
                    type="dialogue",
                    text=dialogue_text,
                    speaker=speaker,
                )
                current_beats.append(beat)
                prev_speaker = speaker

        # ダッシュで始まる強調セリフ
        elif line.startswith("——") and "「" not in line:
            text = line.lstrip("——").strip()
            if text:
                beat = Beat(
                    type="dialogue",
                    text=text,
                    speaker=prev_speaker,
                    emotion="emphasized"
                )
                current_beats.append(beat)

        # ナレーション
        else:
            # 短すぎる行はスキップ
            if len(line) < 5:
                i += 1
                continue

            beat = Beat(type="narration", text=line)
            current_beats.append(beat)

        context_lines.append(line)
        if len(context_lines) > 5:
            context_lines.pop(0)

        i += 1

    # 最後のシーンを保存
    if current_scene and current_beats:
        current_scene.beats = current_beats
        scenes.append(current_scene)

    return title, title_en, scenes


def detect_characters_in_scene(scene: Scene) -> list[str]:
    """シーン内に登場するキャラクターを検出"""
    characters = set()

    for beat in scene.beats:
        if beat.speaker:
            characters.add(beat.speaker)

        # テキストからもキャラクターを検出
        text = beat.text
        if "レン" in text or "灰谷" in text:
            characters.add("ren")
        if "ユキ" in text:
            characters.add("yuki")
        if "澄香" in text or "蒼井" in text:
            if scene.is_flashback and "二十四" in text:
                characters.add("sumika_young")
            else:
                characters.add("sumika")
        if "母" in text:
            if scene.is_flashback:
                characters.add("mother_young")
            else:
                characters.add("mother")
        if "怪異" in text or "黒い靄" in text:
            characters.add("voice_entity")

    return list(characters)


def process_episode(filepath: Path, output_dir: Path) -> dict:
    """1つのエピソードを処理"""
    title, title_en, scenes = parse_markdown(filepath)

    # エピソード番号を抽出
    episode_num = 1
    m = re.search(r"第(\d)話", filepath.name)
    if m:
        episode_num = int(m.group(1))
    elif "最終話" in filepath.name:
        episode_num = 4

    # 各シーンにキャラクターを追加
    for scene in scenes:
        scene.characters_present = detect_characters_in_scene(scene)

    episode_data = {
        "episode": episode_num,
        "title": title,
        "title_en": title_en or "",
        "scenes": [s.to_dict() for s in scenes]
    }

    # 出力
    output_path = output_dir / f"episode{episode_num}_extracted.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(episode_data, f, ensure_ascii=False, indent=2)

    print(f"  {filepath.name} -> {output_path.name}")
    print(f"    シーン数: {len(scenes)}")
    print(f"    ビート数: {sum(len(s.beats) for s in scenes)}")

    return episode_data


def main():
    """メイン処理"""
    # パス設定
    base_dir = Path(__file__).parent.parent
    novel_dir = base_dir / "小説"
    output_dir = base_dir / "data" / "scenes"

    # 出力ディレクトリ作成
    output_dir.mkdir(parents=True, exist_ok=True)

    print("小説ファイルからシーンデータを抽出中...")
    print()

    # 各エピソードを処理
    md_files = sorted(novel_dir.glob("第*話*.md"))

    for filepath in md_files:
        process_episode(filepath, output_dir)
        print()

    print("完了!")
    print()
    print("注意: 自動抽出されたデータは手動で確認・修正が必要です。")
    print("      特に話者識別は精度が低いため、確認してください。")


if __name__ == "__main__":
    main()
