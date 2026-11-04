# ClipScribe

**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

![CI](https://github.com/zqd9853572002/ClipScribe/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

> **第一次用？** 先看[快速开始](QUICKSTART.zh-CN.md)：从零到出第一条字幕，大约五分钟。

ClipScribe 是一个本地离线的 Windows 桌面工具：把音频或视频转写成字幕（SRT、VTT、TXT），配上静态封面图导出 MP4 视频，并可选择神经网络降噪和硬字幕烧录。全部处理都在你自己的机器上完成，只有首次下载模型时需要联网。

![界面截图](docs/screenshots/zh_CN.png)

> 截图来自 5.x 版本。6.0.0 已更名为 ClipScribe，界面布局不变，只有窗口标题和欢迎语不同。

## 目录

- [能做什么](#能做什么)
- [执行模型](#执行模型)
- [典型组合](#典型组合)
- [产物与命名](#产物与命名)
- [字幕格式](#字幕格式)
- [界面语言](#界面语言)
- [从旧版升级](#从旧版升级)
- [环境要求](#环境要求)
- [安装](#安装)
- [数据与缓存](#数据与缓存)
- [项目结构](#项目结构)
- [开发与测试](#开发与测试)
- [已知限制](#已知限制)
- [许可证](#许可证)
- [致谢](#致谢)

## 能做什么

| 范围 | 说明 |
| --- | --- |
| 音频输入 | 17 种：MP3、M4A、M4B、AAC、WAV、FLAC、OGG、OGA、OPUS、WMA、AIFF、AIF、APE、WV、AMR、AC3、DTS |
| 视频输入 | 5 种容器：MP4、WebM、MKV、MOV、M4V。只提取第一条音轨，画面不保留 |
| A · 降噪 | FFmpeg RNNoise（`arnndn`，混合比例可配）或 sherpa-onnx GTCRN；RNNoise 模型缺失时自动降级为 FFmpeg 频谱降噪（`afftdn`） |
| B · 语音识别 → 字幕 | faster-whisper（CPU int8）；模型 tiny / base / small / medium / large-v3-turbo；语种自动检测 / 中文 / 英文；SRT、VTT、TXT 可任意组合输出 |
| C · 配图 MP4 | 静态封面 + 音轨，1 帧/秒 H.264 + AAC 192 kbps；可选响度标准化（−16 LUFS，默认开）；可选硬字幕烧录 |
| 辅助能力 | 术语 / 提示词（`initial_prompt`，上限 800 字符）、长句优先、幻听抑制、三语界面 |

三组功能互相独立：单独跑任意一组、任意两组或三组一起跑都可以。

## 执行模型

选择一个或多个音频 / 视频文件，在三组互相独立的选项里勾选要做的事，然后点一次「开始执行」。文件按顺序逐个处理，每个文件只执行其选项对应的步骤。

| 选项组 | 设置 | 可选值 |
| --- | --- | --- |
| A · 降噪 | 强度 | 关闭 / 轻度（RNNoise）/ 强力（GTCRN 神经网络） |
| B · 识别与字幕 | 模型 | 关闭、tiny、base、small、medium、large-v3-turbo |
| | 识别语种 | 自动检测 / 中文 / 英文 |
| | 字幕格式 | SRT、VTT 与 TXT，可分别勾选 |
| | 术语 / 提示词 | 可选单行，最多 800 字符，作为 `initial_prompt` 传给 Whisper |
| | 长句优先 | 默认不勾；VAD 参数更宽松，减少中文长句被切碎 |
| C · 视频生成 | 视频文件 | 原始音频配图 MP4 和/或降噪音频配图 MP4 |
| | 封面图片 | JPG、PNG、BMP、WEBP |
| | 输出尺寸 | 1080p（默认）/ 720p / 原图尺寸 |
| | 响度标准化 | `-16 LUFS`；默认勾选；只作用于成片 MP4 |
| | 字幕烧录进画面（硬字幕） | 默认不勾；需同时勾选配图 MP4 与字幕格式、输入为音频、且 FFmpeg 带 libass |

- 降噪对每个文件最多执行一次，字幕和降噪视频都复用这次结果。只要降噪组不为「关闭」，无论有没有字幕或视频用到它，都会产出 `文件名_denoised.wav`。
- 三组功能可以任意组合执行：单独任意一组，以及 AB、AC、BC、ABC 组合都可以。唯一不能执行的是「视频输入 + 只勾配图 MP4」，界面会提示「视频输入请至少勾选一种字幕格式或降噪」。
- 只有「音频输入 + 勾选配图 MP4」时才需要封面图；视频输入永远不需要封面。
- 勾选「降噪音频配图 MP4」要求降噪不为「关闭」；降噪关闭时该项会被忽略。
- 视频输入时，两个配图 MP4 会被跳过：复选框保持置灰，即使之前勾着也不会执行，也不再要求封面图；界面会提示「配图 MP4 本次跳过（视频输入只提取音轨）」。勾选状态会保留，切回音频输入时恢复。
- 支持 FFmpeg 能解码的音频格式，包括 MP3、M4A、M4B、AAC、WAV、FLAC、OGG、OGA、OPUS、WMA、AIFF、AIF、APE、WV、AMR、AC3、DTS。
- 支持的视频格式为 MP4、WebM、MKV、MOV、M4V。程序用 `-vn` 和第一条音轨（`0:a:0?`）提取音频，转成 16 kHz 单声道 WAV 后走原有识别流程；多音轨视频不提供选轨。
- 视频里没有音轨时，程序会停下并给出可读提示「输入文件里没有可用的音轨（视频可能无声），无法提取音频」，不再把原始 ffmpeg stderr 丢给用户。
- 「术语 / 提示词」会作为 `initial_prompt` 传给 Whisper，主要改善人名、公司名和专业术语的识别，标点也更稳。超过 800 字符会自动截断，并在日志里提示。
- 「长句优先」把 VAD 参数从标准（`min_silence_duration_ms=400`、`speech_pad_ms=200`）切到长句（`700`、`300`、`threshold=0.4`），中文长句更不容易被切碎。默认不勾选。
- 「响度标准化」在成片 MP4 的音频链尾追加 `loudnorm=I=-16:TP=-1.5:LRA=11`，让不同来源的片子音量接近。它只作用于成片，不碰送去识别的音频；视频输入不产出配图 MP4，该选项会置灰。
- 「字幕烧录进画面（硬字幕）」会用 FFmpeg 的 `subtitles` 滤镜（依赖 libass）把 SRT 直接渲染进画面，产出的 MP4 本身就带字幕。默认不勾选，且必须同时满足四个条件才可用：勾了至少一个配图 MP4、勾了至少一种字幕格式、输入不是视频、当前 FFmpeg 带 libass。不满足时复选框置灰并给出具体原因：「视频输入不产出配图 MP4，硬字幕不适用」「未勾选配图 MP4，硬字幕无法烧录」「未勾选任何字幕格式，硬字幕无法烧录」「当前 FFmpeg 缺少 libass，无法烧录硬字幕」。外挂字幕仍会照常输出，硬字幕与外挂字幕不冲突。
- 轻度降噪走 RNNoise。RNNoise 模型不可用（没下载或下载失败）时，降噪链会降级为 `highpass=f=80,afftdn=nf=-25:tn=1`，即 FFmpeg 内置的频谱降噪，无需下载；日志会明确写「已降级为频谱降噪（afftdn）」，不会静默失效。
- `config.json` 里的 `arnndn_mix`（默认 `0.8`，范围 0.0–1.0）控制降噪输出与原声的混合比例：`1.0` 为完全降噪，数值越小保留越多原声。界面上没有入口，只能手动改配置文件。
- 长静音段更不容易冒出「谢谢观看」「字幕由…提供」「请不吝点赞」这类幻听字幕：识别阈值收紧（`no_speech_threshold` 0.5、`log_prob_threshold` −1.0），同时时长 ≥ 3 秒且文本命中已知幻听模式的片段会被丢弃，丢弃数量写入日志。具体漏掉哪些，见[已知限制](#已知限制)。

默认值：1080p、large-v3-turbo、自动检测、轻度 RNNoise 降噪、响度标准化开启、长句优先关闭、字幕烧录关闭。

## 典型组合

| 想要的结果 | 勾选方式 |
| --- | --- |
| 只要字幕 | 模型选非「关闭」；勾选 SRT、VTT 和/或 TXT；不需要封面 |
| 视频出字幕 | 选中视频文件；勾选 SRT、VTT 和/或 TXT；英文视频把识别语种设为「英文」；两个配图 MP4 都不勾（视频输入时会自动跳过） |
| 原声转 MP4 | 勾选「原始音频配图 MP4」；选择封面 |
| 降噪后转 MP4 | 降噪选轻度或强力；勾选「降噪音频配图 MP4」；选择封面 |
| 全都要 | 勾选两个 MP4 和至少一种字幕格式，降噪选轻度或强力 |

三组功能任意组合都能执行：单独任意一组，或 AB、AC、BC、ABC 组合均可。唯一没有产出的组合是「视频输入 + 既不勾字幕格式也不开降噪」。

两个设置见效最快：

- 录音里人名、公司名、专业术语多的时候，填「术语 / 提示词」，效果最明显。
- 中文访谈、讲座类音频，建议打开「长句优先」，避免整段话被切成碎片。

想先试听降噪效果，可以把降噪设为轻度或强力，其他选项全部不勾。程序只导出 `录音_denoised.wav`，听完再决定要不要做视频。总的来说，只要降噪不为「关闭」，就会产出 `录音_denoised.wav`，与其他选项无关。

## 产物与命名

所有产物写入「输出目录」。没有选择输出目录时，使用第一个音频文件所在的目录。

以 `录音.mp3` 为例：

| 产物 | 文件名 |
| --- | --- |
| 字幕 | `录音.srt`、`录音.vtt`、`录音.txt` |
| 原声视频 | `录音.mp4` |
| 降噪音频 | `录音_denoised.wav`（48 kHz / 立体声 / 16-bit PCM） |
| 降噪视频 | `录音_denoised.mp4` |

已存在的文件不会被覆盖。文件名被占用时，会在扩展名前追加 ` (1)`、` (2)` 等序号。

以视频 `讲座.mp4` 为例，勾选 SRT 和 VTT 时只会得到 `讲座.srt` 和 `讲座.vtt`；如果开了降噪，还会多一个 `讲座_denoised.wav`。不会生成 `讲座.mp4`，原始画面也不会被重新编码。

视频使用 H.264（libx264）编码，1 帧/秒，音频为 AAC 192 kbps，并启用 `faststart`。1080p 和 720p 模式下，非 16:9 的封面会等比缩放并补黑边；原图尺寸模式保留封面原始尺寸，宽高向下取整为偶数。SRT、VTT 和 TXT 字幕文件始终作为外挂文件输出；勾选硬字幕时，同一份 SRT 也会渲染进画面，所以一次执行可以同时得到硬字幕 MP4 和外挂字幕。烧录不增加处理步骤，进度条不变。

## 字幕格式

| 格式 | 扩展名 | 特点 |
| --- | --- | --- |
| SubRip | `.srt` | 带 cue 序号；毫秒用逗号分隔 |
| WebVTT | `.vtt` | 首行 `WEBVTT` 加空行；毫秒用点号分隔；不写 cue 序号 |
| 纯文本 | `.txt` | 所有段落拼成一行，英文单词之间补一个空格 |

三种格式共用同一套排版规则：每行 42 显示宽（一个中日韩字符记 2 宽），每条最多 3 行，空文本段落跳过，每条字幕至少显示 0.2 秒。文件统一使用 UTF-8 无 BOM。

VTT 只做基础字幕：不写 `STYLE` 样式块，不写 `NOTE` 注释，不写 cue id，也不做 karaoke 时间标签。SRT、VTT、TXT 可以在同一次执行里任意组合输出。

VTT 默认不勾选。它和 SRT / TXT 一样随识别模型开关联动置灰，勾选状态会写入配置文件并在下次启动时恢复。

**外挂字幕与硬字幕。** SRT、VTT、TXT 是外挂文件：播放器或平台单独读取，观众可以随时开关。硬字幕则由 FFmpeg 的 `subtitles` 滤镜（libass）直接画进画面，无法关闭。上传 B 站、YouTube 用外挂字幕，平台会单独存放字幕并支持多语言；发微信、抖音用硬字幕，因为播放器没有字幕轨，文字必须出现在画面里。勾选硬字幕不会影响外挂文件的输出。

硬字幕在勾选 SRT 时直接复用那份 SRT；只勾 VTT 和/或 TXT 时，程序会在内部临时生成一份 SRT 用于烧录，不会把它留在输出目录。字号按输出高度动态计算，约为高度的 3%（夹在 16–48），边距约为高度的 4%（夹在 10–80），描边 2、无阴影。中文字体按 `Microsoft YaHei` → `Noto Sans CJK SC` 顺序自动探测，都找不到时交给 libass 自选，并在日志提示可能掉字。Windows 下的中文路径和空格路径都能正常工作（实现上使用临时 ASCII 目录加相对路径，避开转义问题）。

## 界面语言

内置简体中文、繁體中文、English。右上角可切换，切换后即时生效，不需要重启程序。首次启动默认简体中文，之后会记住你的选择。已经输出的历史日志不会随语言切换回译。

## 从旧版升级

6.0.0 是一次改名版本：

| 项目 | 5.x | 6.0.0 |
| --- | --- | --- |
| 产品名 | MP3 转 MP4 | **ClipScribe** |
| 启动脚本 | `MP3toMP4.py` | `ClipScribe.py` |
| Python 包 | `mp3tom4/` | `clipscribe/` |
| 命令 | `mp3tom4`、`mp3tom4-gui` | `clipscribe`、`clipscribe-gui` |
| 配置与模型目录 | `%APPDATA%\Mp3ToMp4` | `%APPDATA%\ClipScribe` |

**你的设置和已下载的模型会自动带过来。** 6.0.0 首次启动时，会把 `%APPDATA%\Mp3ToMp4` 整个目录重命名为 `%APPDATA%\ClipScribe`。这不是复制，已经下载好的模型不会重新下载。

迁移有三重降级，任何一步失败都不会让程序崩溃：

1. 直接用 `os.replace` 重命名——同盘时瞬间完成。
2. 重命名失败时退回 `shutil.move` 移动——用于新旧路径跨盘的情况。
3. 两步都失败就放弃迁移：继续使用旧目录，日志写出失败原因，程序照常启动。

其他规则：

- 如果 `%APPDATA%\ClipScribe` 已经存在，则不迁移、不覆盖、不合并，以新目录为准，旧目录一律不动。
- 旧目录只作为迁移来源，正常使用中不会再被读写。
- 启动日志一定会输出一行配置目录状态：已迁移 / 使用新目录 / 未发现旧目录 / 迁移失败继续用旧目录。

**如果需要退回 5.x。** 旧版只认 `%APPDATA%\Mp3ToMp4`，这个目录已经不在了，所以它会新建一个空目录并重新下载识别模型。想避免重新下载，就在运行 5.x 之前把 `%APPDATA%\ClipScribe` 复制回 `%APPDATA%\Mp3ToMp4`。复制不会影响 6.0.0 的目录，6.0.0 下次启动也不会去动这个恢复出来的旧目录。

**命令变化。** `python MP3toMP4.py` 改为 `python ClipScribe.py`；也支持模块方式 `python -m clipscribe`，以及安装后的 `clipscribe` / `clipscribe-gui`。任何引用了旧脚本名或 `mp3tom4` 包的脚本、快捷方式和计划任务都需要同步修改。

GitHub 仓库已改名为 `ClipScribe`，新地址是 <https://github.com/zqd9853572002/ClipScribe>，旧链接会自动跳转到新地址。

## 环境要求

- Windows 10 / 11
- Python 3.10 或更高
- FFmpeg，且需要 `libx264` 和 `aac` 编码器
- 可选：带 `libass` 的 FFmpeg，仅烧录硬字幕时需要

程序本身不包含 FFmpeg，需要单独安装。

`libx264` 和 `aac` 是必需能力，缺任意一个的版本会被拒绝。`libass` 是可选能力：缺少时其余功能全部正常，只是不能烧录硬字幕，启动日志会提示「字幕烧录不可用，其余功能正常」。想确认自己的 FFmpeg 是否带 libass，执行 `ffmpeg -filters`，看列表里有没有 `subtitles` 滤镜（形如 `.. subtitles  V->V  Render text...`）。

磁盘空间：留出你要用的识别模型体积（75 MB 到 1.55 GB，见[数据与缓存](#数据与缓存)），再加上产物文件的空间。

## 安装

### 方式一：克隆后直接运行

```bash
git clone https://github.com/zqd9853572002/ClipScribe.git
cd ClipScribe
pip install -r requirements.txt
python ClipScribe.py
```

### 方式二：作为 Python 包安装

```bash
pip install .
clipscribe
```

`clipscribe-gui` 启动的是同一个程序。不安装时也可以用 `python -m clipscribe` 直接从源码运行。

### 方式三：安装完整功能

```bash
pip install ".[full]"
```

这会额外安装 `sherpa-onnx`（强力 GTCRN 降噪）和 `imageio-ffmpeg`（FFmpeg 的额外来源）。

### Windows 安装 FFmpeg

```powershell
winget install Gyan.FFmpeg
```

程序会按以下顺序探测：配置文件里上次使用的路径、程序所在目录的 `ffmpeg.exe`、`PATH`、winget 包目录、常见安装路径、`imageio-ffmpeg`。也可以点界面顶部的「更换」手动指定 `ffmpeg.exe`。只有同时提供 `libx264` 和 `aac` 的版本才会被接受，否则程序会明确提示缺哪个编码器。libass 不在这项必需检查里：没有它程序照常运行，只是硬字幕选项会置灰；可用 `ffmpeg -filters` 确认列表里有 `subtitles`。用 pip 安装 `imageio-ffmpeg` 可以再多一个兜底来源。

## 数据与缓存

| 数据 | 位置 |
| --- | --- |
| 配置文件 | `%APPDATA%\ClipScribe\config.json` |
| 模型缓存 | `%APPDATA%\ClipScribe\models\`（内含 `whisper\` 与 `denoise\`） |

配置文件保存 FFmpeg 路径、上次使用的封面、输出目录、输出尺寸、界面语言和识别相关设置。

5.2.0 新增的配置项：

| 配置键 | 含义 |
| --- | --- |
| `asr_initial_prompt` | 术语 / 提示词文本，最多 800 字符；与识别组里的输入框对应 |
| `asr_vad_mode` | `standard`（默认）或 `long`，对应「长句优先」的勾选状态 |
| `loudnorm_enabled` | `true`（默认）或 `false`，对应「响度标准化」的勾选状态 |
| `arnndn_mix` | RNNoise 混合比例，默认 `0.8`，有效范围 0.0–1.0；只能改配置文件 |

5.3.0 新增的配置项：

| 配置键 | 含义 |
| --- | --- |
| `burn_subtitles` | `false`（默认）或 `true`，对应「字幕烧录进画面（硬字幕）」的勾选状态 |

6.0.0 没有新增配置键：目录迁移完成后，原有配置原样继续使用。

首次使用某个识别模型时，程序会自动下载权重到 `models\whisper\`：

| 模型 | 下载体积 |
| --- | --- |
| large-v3-turbo | 1.55 GB |
| medium | 1.46 GB |
| small | 464 MB |
| base | 141 MB |
| tiny | 75 MB |

下载需要联网，耗时可能从几分钟到几十分钟。程序会在开始前写入日志，所以首次运行看起来没反应时，通常是在下载。模型会保留在磁盘上，整个目录可以安全删除。两个小体积降噪模型会在首次使用时下载到 `models\denoise\`。

## 项目结构

```text
ClipScribe.py       启动入口（python ClipScribe.py）
clipscribe/
├── __main__.py     python -m clipscribe
├── app.py          启动流程：日志、目录迁移、主窗口
├── config.py       常量、配置读写、路径、迁移
├── i18n.py         多语言框架
├── ffmpeg.py       FFmpeg 探测、滤镜、封装
├── denoise.py      降噪（RNNoise / GTCRN）
├── asr.py          语音识别（faster-whisper）
├── subtitle.py     SRT / VTT / TXT 生成
├── pipeline.py     任务编排
├── ui/             界面
└── locale/         三语词条
tests/              pytest 测试套件（303 项）
docs/screenshots/   界面截图
```

## 开发与测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

调用真实 FFmpeg 的用例标记为 `integration`，可以用 `pytest tests/ -m "not integration"` 跳过。

## 已知限制

1. **强力降噪会损失高频。** GTCRN 按 16 kHz 处理，结果再升采样到 48 kHz，高频细节是真的丢了，听感会偏闷。要保音质选轻度 RNNoise，要降噪力度选强力 GTCRN。
2. **取消不是瞬时的。** 降噪和封装这类 FFmpeg 步骤可以立刻终止，但 Whisper 推理是阻塞调用，取消需要等当前这句识别完成。
3. **首次识别耗时长。** 包含模型下载，可能几分钟到几十分钟，取决于网络和模型大小。
4. **字幕默认是外挂文件。** 硬字幕需要手动勾选，且要求有配图 MP4 输出、FFmpeg 带 libass、输入为音频；不勾硬字幕时，字幕永远不会渲染进画面。
5. **视频输入不留画面。** 视频只作为音源，画面不会被保留、重新封装或重新编码，所以视频输入时两个配图 MP4 选项会被跳过：保持置灰、即使勾着也不执行，也不需要封面；勾选状态会保留给下一次音频输入。视频输入下如果既没勾字幕格式、也没开降噪，就没有可执行的任务，程序会提示至少勾选一种。
6. **只取第一条音轨。** 双语音轨这类多音轨视频无法选轨，第二条及之后的音轨会被忽略。
7. **无声视频处理不了。** 没有音轨的视频会直接停下并给出可读提示，而不是抛 ffmpeg stderr。
8. **历史日志不回译。** 切换界面语言后，已经输出的日志保持原语言。
9. **幻听过滤只覆盖一部分情况。** 过滤基于文本模式匹配，只处理「时长 ≥ 3 秒且命中已知模式」的片段，没命中模式的幻觉不会被删除。词级时间戳（`word_timestamps`）保持关闭，因为 faster-whisper 的 `hallucination_silence_threshold` 依赖它，开启会显著变慢。
10. **原图尺寸输出的字号按 1080 高度基准计算。** 烧录样式按输出高度推导，所以 4K 源的字号会略小、极小图的字号会略大；两者都被夹在 16–48 之间，不会小到不可读。

ClipScribe 不做互译、不做说话人分离、不用 GPU 加速、不支持拖拽文件，也没有字幕编辑器。完整能力见[能做什么](#能做什么)。

## 许可证

GPL-3.0-or-later，完整文本见 [LICENSE](LICENSE)。你可以自由使用、修改和分发；如果分发修改后的版本，必须以相同许可证开源。

## 致谢

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 语音识别
- [GTCRN / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — 强力降噪
- [RNNoise](https://jmvalin.ca/demos/rnnoise/) — 轻度降噪
- [FFmpeg](https://ffmpeg.org/) — 解码、编码与封装
