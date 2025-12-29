# 音声生成プロンプト

本ファイルは『深夜零時の遺失物係』のBGM・効果音生成用プロンプトを収録。

---

## 使用サービス

| 種別 | サービス | プラン | 備考 |
|------|----------|--------|------|
| BGM | Suno AI | Pro ($10/月) | YouTube商用利用可 |
| 効果音 | ElevenLabs | Free～ | API利用可（10,000クレジット/月） |

---

## BGMプロンプト（Suno AI用）

### 1. メインテーマ（オープニング）

**使用シーン:** タイトル、物語開始

```
melancholic piano, gentle strings, mysterious ambient, rain atmosphere, nostalgic Japanese drama soundtrack, emotional, bittersweet melody, slow tempo, 80 BPM
```

**スタイル:** `Ambient, Piano, Cinematic`

---

### 2. 遺失物取扱所（通常BGM）

**使用シーン:** 窓口シーン、日常パート

```
lo-fi ambient, soft piano chords, gentle rain sounds in background, late night cafe atmosphere, relaxing, warm, slightly melancholic, peaceful office mood, 70 BPM
```

**スタイル:** `Lo-fi, Ambient, Piano`

---

### 3. 雨と記憶（回想シーン）

**使用シーン:** 澄香の過去回想、父との思い出

```
acoustic guitar melody, gentle fingerpicking, nostalgic folk ballad, bittersweet, memory of youth, warm analog sound, emotional strings, Japanese drama OST style, 75 BPM
```

**スタイル:** `Acoustic, Folk, Cinematic`

---

### 4. 怪異出現（不穏BGM）

**使用シーン:** 第2話〜第3話、怪異との遭遇

```
dark ambient, eerie atmosphere, dissonant piano notes, creeping tension, supernatural horror, Japanese horror movie soundtrack, unsettling, building dread, 60 BPM
```

**スタイル:** `Dark Ambient, Horror, Cinematic`

---

### 5. 対峙（クライマックス）

**使用シーン:** 第3話、怪異との対話シーン

```
emotional orchestral, building crescendo, dramatic strings, piano and orchestra, confrontation theme, tragic beauty, Japanese anime OST climax, powerful emotional peak, 90 BPM
```

**スタイル:** `Orchestral, Cinematic, Dramatic`

---

### 6. 和解と別れ（感動シーン）

**使用シーン:** 第4話、母との和解、ラストシーン

```
gentle piano solo, warm emotional melody, tearful reunion theme, hopeful yet bittersweet, soft strings joining gradually, Japanese drama ending theme, heartwarming resolution, 70 BPM
```

**スタイル:** `Piano, Emotional, Cinematic`

---

### 7. エンディング（夜明け）

**使用シーン:** エピローグ、物語終結

```
hopeful ambient, morning light atmosphere, gentle piano with soft synth pads, new beginning theme, peaceful resolution, sunrise feeling, warm and optimistic ending, Japanese slice of life anime ED, 80 BPM
```

**スタイル:** `Ambient, Piano, Hopeful`

---

## 効果音プロンプト（ElevenLabs用）

### 環境音

#### 雨音（窓越し）
```
gentle rain on window glass, soft raindrops, indoor perspective, calming rain sound, steady light rain
```
**推奨時間:** 30秒（ループ用）

#### 雨音（激しい）
```
heavy rain pouring, intense rainfall, thunderstorm without thunder, dramatic rain sound
```
**推奨時間:** 30秒（ループ用）

#### 駅のアナウンス（遠く）
```
distant train station announcement, muffled PA system, Japanese train station ambience, far away
```
**推奨時間:** 5秒

#### 時計の音
```
old wall clock ticking, antique clock, steady tick tock, quiet room atmosphere
```
**推奨時間:** 10秒（ループ用）

---

### アクション音

#### 鍵の音（錆びた鍵）
```
old rusty key turning in lock, metal clicking, antique lock mechanism, mysterious unlocking sound
```
**推奨時間:** 3秒

#### ドアの開閉
```
old wooden door slowly opening, creaking hinges, quiet office door
```
**推奨時間:** 3秒

#### 足音（駅構内）
```
footsteps on train station floor, echoing steps, empty station at night, walking slowly
```
**推奨時間:** 5秒

---

### 超常現象音

#### 怪異の気配
```
eerie supernatural presence, ghostly whisper wind, unsettling atmosphere, horror ambience
```
**推奨時間:** 5秒

#### 怪異の声（エコー）
```
distant female voice singing, ghostly echo, melancholic humming, supernatural reverb
```
**推奨時間:** 5秒

#### 消失音
```
magical dissolving sound, gentle supernatural fade away, spirit departing, peaceful vanishing
```
**推奨時間:** 3秒

#### 雷鳴（遠く）
```
distant thunder rumble, far away thunderstorm, low rumbling, dramatic weather
```
**推奨時間:** 5秒

---

## API使用例

### ElevenLabs Sound Effects API（Python）

```python
from elevenlabs import ElevenLabs

client = ElevenLabs(api_key="YOUR_API_KEY")

# 効果音生成
result = client.text_to_sound_effects.convert(
    text="gentle rain on window glass, soft raindrops, calming",
    duration_seconds=30,
    prompt_influence=0.5
)

# ファイル保存
with open("sfx_rain_window.mp3", "wb") as f:
    for chunk in result:
        f.write(chunk)
```

### 一括生成スクリプト例

```python
from elevenlabs import ElevenLabs
import os

client = ElevenLabs(api_key="YOUR_API_KEY")

sound_effects = [
    {"name": "sfx_rain_window", "prompt": "gentle rain on window glass, soft raindrops", "duration": 30},
    {"name": "sfx_rain_heavy", "prompt": "heavy rain pouring, intense rainfall", "duration": 30},
    {"name": "sfx_clock_tick", "prompt": "old wall clock ticking, antique clock", "duration": 10},
    {"name": "sfx_key_turn", "prompt": "old rusty key turning in lock, metal clicking", "duration": 3},
    {"name": "sfx_ghost_presence", "prompt": "eerie supernatural presence, ghostly whisper", "duration": 5},
]

os.makedirs("sound_effects", exist_ok=True)

for sfx in sound_effects:
    print(f"Generating: {sfx['name']}")
    result = client.text_to_sound_effects.convert(
        text=sfx["prompt"],
        duration_seconds=sfx["duration"],
        prompt_influence=0.5
    )
    with open(f"sound_effects/{sfx['name']}.mp3", "wb") as f:
        for chunk in result:
            f.write(chunk)
    print(f"Saved: {sfx['name']}.mp3")
```

---

## 推奨ファイル名

### BGM
| # | ファイル名 | 内容 |
|---|-----------|------|
| 1 | `bgm_main_theme.mp3` | メインテーマ |
| 2 | `bgm_office_night.mp3` | 遺失物取扱所 |
| 3 | `bgm_memory_rain.mp3` | 雨と記憶 |
| 4 | `bgm_apparition.mp3` | 怪異出現 |
| 5 | `bgm_confrontation.mp3` | 対峙 |
| 6 | `bgm_reconciliation.mp3` | 和解と別れ |
| 7 | `bgm_ending_dawn.mp3` | エンディング |

### 効果音
| # | ファイル名 | 内容 |
|---|-----------|------|
| 1 | `sfx_rain_window.mp3` | 雨音（窓越し） |
| 2 | `sfx_rain_heavy.mp3` | 雨音（激しい） |
| 3 | `sfx_station_announce.mp3` | 駅アナウンス |
| 4 | `sfx_clock_tick.mp3` | 時計の音 |
| 5 | `sfx_key_turn.mp3` | 鍵の音 |
| 6 | `sfx_door_open.mp3` | ドア開閉 |
| 7 | `sfx_footsteps.mp3` | 足音 |
| 8 | `sfx_ghost_presence.mp3` | 怪異の気配 |
| 9 | `sfx_ghost_voice.mp3` | 怪異の声 |
| 10 | `sfx_vanish.mp3` | 消失音 |
| 11 | `sfx_thunder.mp3` | 雷鳴 |

---

*対象作品: 深夜零時の遺失物係（ロスト・アンド・ファウンド）*
