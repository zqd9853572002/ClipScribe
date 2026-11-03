# Mp3 to MP4

**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

![CI](https://github.com/zqd9853572002/Mp3_to_Mp4/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

Mp3 to MP4 是一個 Windows 桌面工具：把音訊檔案配上靜態封面圖片匯出 MP4 影片，也可以把音訊辨識成 SRT / VTT / TXT 字幕。辨識和匯出之前都可以先做降噪。影片檔案也能直接用：把 MP4、WebM、MKV、MOV、M4V 當作字幕或降噪的音源，程式只讀取其中的第一條音軌。

![介面截圖](docs/screenshots/zh_TW.png)

## 目錄

- [執行模型](#執行模型)
- [常見組合](#常見組合)
- [產物與命名](#產物與命名)
- [字幕格式](#字幕格式)
- [介面語言](#介面語言)
- [系統需求](#系統需求)
- [安裝](#安裝)
- [資料與快取](#資料與快取)
- [專案結構](#專案結構)
- [開發與測試](#開發與測試)
- [已知限制](#已知限制)
- [授權條款](#授權條款)
- [致謝](#致謝)

## 執行模型

選擇一個或多個音訊 / 影片檔案，在三組互相獨立的選項裡勾選要做的事，然後按一次「開始執行」。檔案會依序逐個處理，每個檔案只執行其選項對應的步驟。

| 選項組 | 設定 | 可選值 |
| --- | --- | --- |
| A · 降噪 | 強度 | 關閉 / 輕度（RNNoise）/ 強力（GTCRN 神經網路） |
| B · 辨識與字幕 | 模型 | 關閉、tiny、base、small、medium、large-v3-turbo |
| | 辨識語系 | 自動偵測 / 中文 / 英文 |
| | 字幕格式 | SRT、VTT 與 TXT，可分開勾選 |
| C · 影片產生 | 影片檔案 | 原始音訊配圖 MP4 和/或降噪音訊配圖 MP4 |
| | 封面圖片 | JPG、PNG、BMP、WEBP |
| | 輸出尺寸 | 1080p（預設）/ 720p / 原圖尺寸 |

- 降噪對每個檔案最多執行一次，字幕和降噪影片都重複使用這次結果。只要降噪組不為「關閉」，無論有沒有字幕或影片用到它，都會產出 `檔案名稱_denoised.wav`。
- 三組功能可以任意組合執行：單獨任一組，以及 AB、AC、BC、ABC 組合都可以。唯一不能執行的是「影片輸入 + 只勾配圖 MP4」，介面會提示「影片輸入請至少勾選一種字幕格式或降噪」。
- 只有「音訊輸入 + 勾選配圖 MP4」時才需要封面圖片；影片輸入永遠不需要封面。
- 勾選「降噪音訊配圖 MP4」要求降噪不為「關閉」；降噪關閉時該項會被忽略。
- 影片輸入時，兩個配圖 MP4 會被略過：選項維持變灰，即使之前勾著也不會執行，也不再要求封面圖片；介面會提示「配圖 MP4 本次略過（影片輸入只擷取音軌）」。勾選狀態會保留，切回音訊輸入時恢復。
- 支援 FFmpeg 能解碼的音訊格式，包括 MP3、M4A、M4B、AAC、WAV、FLAC、OGG、OGA、OPUS、WMA、AIFF、APE、WV、AMR、AC3、DTS。
- 支援的影片格式為 MP4、WebM、MKV、MOV、M4V。程式用 `-vn` 和第一條音軌（`0:a:0?`）擷取音訊，轉成 16 kHz 單聲道 WAV 後走原有辨識流程；多音軌影片不提供選軌。
- 影片沒有音軌時，程式會停下並給出可讀提示「輸入檔案裡沒有可用的音軌（影片可能無聲），無法擷取音訊」，不再把原始 ffmpeg stderr 丟給使用者。

預設值：1080p、large-v3-turbo、自動偵測、輕度 RNNoise 降噪。

## 常見組合

| 想要的結果 | 勾選方式 |
| --- | --- |
| 只要字幕 | 模型選非「關閉」；勾選 SRT、VTT 和/或 TXT；不需要封面 |
| 影片出字幕 | 選取影片檔案；勾選 SRT、VTT 和/或 TXT；英文影片把辨識語系設為「英文」；兩個配圖 MP4 都不勾（影片輸入時會自動略過） |
| 原聲轉 MP4 | 勾選「原始音訊配圖 MP4」；選擇封面 |
| 降噪後轉 MP4 | 降噪選輕度或強力；勾選「降噪音訊配圖 MP4」；選擇封面 |
| 全都要 | 勾選兩個 MP4 和至少一種字幕格式，降噪選輕度或強力 |

三組功能任意組合都能執行：單獨任一組，或 AB、AC、BC、ABC 組合均可。唯一沒有產出的組合是「影片輸入 + 既不勾字幕格式也不開降噪」。

想先試聽降噪效果，可以把降噪設為輕度或強力，其他選項全部不勾。程式只會匯出 `錄音_denoised.wav`，聽完再決定要不要做影片。只要降噪不為「關閉」，就會產出 `錄音_denoised.wav`，與其他選項無關。

## 產物與命名

所有產物寫入「輸出資料夾」。沒有選擇輸出資料夾時，使用第一個音訊檔案所在的資料夾。

以 `錄音.mp3` 為例：

| 產物 | 檔案名稱 |
| --- | --- |
| 字幕 | `錄音.srt`、`錄音.vtt`、`錄音.txt` |
| 原聲影片 | `錄音.mp4` |
| 降噪音訊 | `錄音_denoised.wav`（48 kHz / 立體聲 / 16-bit PCM） |
| 降噪影片 | `錄音_denoised.mp4` |

已存在的檔案不會被覆寫。檔案名稱被占用時，會在副檔名前加上 ` (1)`、` (2)` 等序號。

以影片 `講座.mp4` 為例，勾選 SRT 和 VTT 時只會得到 `講座.srt` 和 `講座.vtt`；如果開了降噪，還會多一個 `講座_denoised.wav`。不會產生 `講座.mp4`，原始畫面也不會被重新編碼。

影片使用 H.264（libx264）編碼，1 幀/秒，音訊為 AAC 192 kbps，並啟用 `faststart`。1080p 和 720p 模式下，非 16:9 的封面會等比縮放並補黑邊；原圖尺寸模式保留封面原始尺寸，寬高向下取整為偶數。SRT、VTT 和 TXT 都是外掛字幕檔案，不會燒錄進畫面。

## 字幕格式

| 格式 | 副檔名 | 特點 |
| --- | --- | --- |
| SubRip | `.srt` | 帶 cue 序號；毫秒用逗號分隔 |
| WebVTT | `.vtt` | 首行 `WEBVTT` 加空行；毫秒用點號分隔；不寫 cue 序號 |
| 純文字 | `.txt` | 所有段落併成一行，英文單字之間補一個空格 |

三種格式共用同一套排版規則：每行 42 顯示寬（一個中日韓字元記 2 寬），每條最多 3 行，空文字段落跳過，每條字幕至少顯示 0.2 秒。檔案統一使用 UTF-8 無 BOM。

VTT 只做基礎字幕：不寫 `STYLE` 樣式區塊，不寫 `NOTE` 註解，不寫 cue id，也不做 karaoke 時間標籤。SRT、VTT、TXT 可以在同一次執行裡任意組合輸出。

VTT 預設不勾選。它和 SRT / TXT 一樣隨辨識模型開關連動變灰，勾選狀態會寫入設定檔並在下次啟動時還原。

## 介面語言

內建簡體中文、繁體中文、English。右上角可切換，切換後立即生效，不需要重新啟動程式。首次啟動預設簡體中文，之後會記住你的選擇。已經輸出的歷史日誌不會隨語言切換回譯。

## 系統需求

- Windows 10 / 11
- Python 3.10 或更新版本
- FFmpeg，且需要 `libx264` 和 `aac` 編碼器

程式本身不包含 FFmpeg，需要另外安裝。

## 安裝

### 方式一：取得專案後直接執行

```bash
git clone https://github.com/zqd9853572002/Mp3_to_Mp4.git
cd Mp3_to_Mp4
pip install -r requirements.txt
python MP3toMP4.py
```

### 方式二：安裝成 Python 套件

```bash
pip install .
mp3tom4
```

`mp3tom4-gui` 啟動的是同一個程式。

### 方式三：安裝完整功能

```bash
pip install ".[full]"
```

這會額外安裝 `sherpa-onnx`（強力 GTCRN 降噪）和 `imageio-ffmpeg`（FFmpeg 的額外來源）。

### Windows 安裝 FFmpeg

```powershell
winget install Gyan.FFmpeg
```

程式會依下列順序偵測：設定檔裡上次使用的路徑、程式所在資料夾的 `ffmpeg.exe`、`PATH`、winget 套件目錄、常見安裝路徑、`imageio-ffmpeg`。也可以點介面頂端的「更換」手動指定 `ffmpeg.exe`。只有同時提供 `libx264` 和 `aac` 的版本才會被接受，否則程式會明確提示缺少哪個編碼器。用 pip 安裝 `imageio-ffmpeg` 可以再多一個備援來源。

## 資料與快取

| 資料 | 位置 |
| --- | --- |
| 設定檔 | `%APPDATA%\Mp3ToMp4\config.json` |
| 模型快取 | `%APPDATA%\Mp3ToMp4\models\`（內含 `whisper\` 與 `denoise\`） |

設定檔會保存 FFmpeg 路徑、上次使用的封面、輸出資料夾、輸出尺寸、介面語言和辨識相關設定。

首次使用某個辨識模型時，程式會自動下載權重到 `models\whisper\`：

| 模型 | 下載大小 |
| --- | --- |
| large-v3-turbo | 1.55 GB |
| medium | 1.46 GB |
| small | 464 MB |
| base | 141 MB |
| tiny | 75 MB |

下載需要連網，耗時可能從幾分鐘到幾十分鐘。程式會在開始前寫入日誌，所以首次執行看起來沒反應時，通常是在下載。模型會保留在磁碟上，整個目錄可以安全刪除。兩個小體積降噪模型會在首次使用時下載到 `models\denoise\`。

## 專案結構

```text
mp3tom4/
├── config.py      常數、設定讀寫、路徑
├── i18n.py        多語言框架
├── ffmpeg.py      FFmpeg 偵測、濾鏡、封裝
├── denoise.py     降噪（RNNoise / GTCRN）
├── asr.py         語音辨識（faster-whisper）
├── subtitle.py    SRT / VTT / TXT 產生
├── pipeline.py    任務編排
├── ui/            介面
└── locale/        三語詞條
tests/             pytest 測試套件
```

## 開發與測試

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

呼叫真實 FFmpeg 的案例標記為 `integration`，可以用 `pytest tests/ -m "not integration"` 跳過。

## 已知限制

1. **強力降噪會損失高頻。** GTCRN 以 16 kHz 處理，結果再升取樣到 48 kHz，高頻細節是真的丟失，聽感會偏悶。要保音質選輕度 RNNoise，要降噪力度選強力 GTCRN。
2. **取消不是即時的。** 降噪和封裝這類 FFmpeg 步驟可以立刻終止，但 Whisper 推論是阻塞呼叫，取消需要等目前這句辨識完成。
3. **首次辨識耗時長。** 包含模型下載，可能幾分鐘到幾十分鐘，取決於網路和模型大小。
4. **字幕是外掛檔案。** 不會燒錄進影片畫面。
5. **影片輸入不留畫面。** 影片只當作音源，畫面不會被保留、重新封裝或重新編碼，所以影片輸入時兩個配圖 MP4 選項會被略過：維持變灰、即使勾著也不執行，也不需要封面；勾選狀態會保留給下一次音訊輸入。影片輸入下如果既沒勾字幕格式、也沒開降噪，就沒有可執行的任務，程式會提示至少勾選一種。
6. **只取第一條音軌。** 雙語音軌這類多音軌影片無法選軌，第二條之後的音軌會被忽略。
7. **無聲影片處理不了。** 沒有音軌的影片會直接停下並給出可讀提示，而不是拋出 ffmpeg stderr。
8. **歷史日誌不回譯。** 切換介面語言後，已經輸出的日誌維持原語言。

## 授權條款

GPL-3.0-or-later，完整文本見 [LICENSE](LICENSE)。你可以自由使用、修改和散布；如果散布修改後的版本，必須以相同授權條款開源。

## 致謝

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 語音辨識
- [GTCRN / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — 強力降噪
- [RNNoise](https://jmvalin.ca/demos/rnnoise/) — 輕度降噪
- [FFmpeg](https://ffmpeg.org/) — 解碼、編碼與封裝
