# Mp3 to MP4

**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

![CI](https://github.com/zqd9853572002/Mp3_to_Mp4/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

Mp3 to MP4 is a Windows desktop tool that pairs audio files with a still cover image and exports MP4 videos. It can also transcribe audio into SRT, VTT, and TXT subtitles and reduce background noise before recognition or export. Video files are accepted as well: MP4, WebM, MKV, MOV, and M4V can be used directly as a subtitle or denoise source, and only their first audio track is read.

![Application window](docs/screenshots/en.png)

## Contents

- [Execution model](#execution-model)
- [Common combinations](#common-combinations)
- [Output files and naming](#output-files-and-naming)
- [Subtitle formats](#subtitle-formats)
- [Interface language](#interface-language)
- [Requirements](#requirements)
- [Installation](#installation)
- [Data and cache](#data-and-cache)
- [Project structure](#project-structure)
- [Development and testing](#development-and-testing)
- [Known limitations](#known-limitations)
- [License](#license)
- [Credits](#credits)

## Execution model

Select one or more audio or video files, configure the three option groups below, then press **Start** once. Files are processed one after another, and each file runs only the steps its options require.

| Group | Setting | Choices |
| --- | --- | --- |
| A · Noise reduction | Strength | Off / Light (RNNoise) / Strong (GTCRN neural network) |
| B · Recognition and subtitles | Model | Off, tiny, base, small, medium, large-v3-turbo |
| | Spoken language | Auto-detect / Chinese / English |
| | Subtitle formats | SRT, VTT, and TXT, selected independently |
| | Glossary / prompt | Optional single line, up to 800 characters, sent to Whisper as `initial_prompt` |
| | Long sentences first | Off by default; looser VAD settings so long Chinese sentences are cut less often |
| C · Video output | Video files | MP4 with the original audio and/or MP4 with the denoised audio |
| | Cover image | JPG, PNG, BMP, WEBP |
| | Resolution | 1080p (default) / 720p / original image size |
| | Loudness normalization | `-16 LUFS`; on by default; applies to the finished MP4 only |

- Noise reduction runs at most once per file; subtitles and the denoised video reuse that result. Whenever the noise-reduction group is not Off, `{name}_denoised.wav` is always written, even if no subtitle or video output uses it.
- Any combination of the three groups can run: each group on its own, or A+B, A+C, B+C, and A+B+C. The only combination that cannot run is a video input with nothing checked except a cover MP4 option; the app then asks for at least one subtitle format or noise reduction.
- A cover image is required only for audio input with a cover MP4 option selected. Video input never needs a cover.
- The denoised-video option requires noise reduction to be on; when noise reduction is Off, that option is ignored.
- For video input, both cover MP4 options are skipped: they stay greyed out, they do not run even if they were checked earlier, and no cover image is requested. The app reports "Cover MP4 is skipped for this run (video input only provides its audio track)". Their checked state is kept and restored when you go back to an audio file.
- Accepted audio formats are the ones FFmpeg can decode, including MP3, M4A, M4B, AAC, WAV, FLAC, OGG, OGA, OPUS, WMA, AIFF, APE, WV, AMR, AC3, and DTS.
- Accepted video formats are MP4, WebM, MKV, MOV, and M4V. Only the first audio track is extracted (`-vn`, first audio stream) and converted to 16 kHz mono WAV before recognition, so a multi-track video cannot switch tracks.
- A video with no audio track stops with a readable message ("The input has no usable audio track…") instead of raw FFmpeg stderr.
- The glossary / prompt is handed to Whisper as `initial_prompt`. It mainly helps with names, company names, and domain jargon, and also steadies punctuation. Text longer than 800 characters is truncated, and the log says so.
- Long sentences first switches the VAD settings from standard (`min_silence_duration_ms=400`, `speech_pad_ms=200`) to long (`700`, `300`, and `threshold=0.4`), so a long Chinese sentence is less likely to be split into pieces. It is off by default.
- Loudness normalization appends `loudnorm=I=-16:TP=-1.5:LRA=11` to the audio chain of the finished MP4, keeping clips from different sources at a similar level. It is applied only to video output, never to the audio sent to recognition, and it is greyed out for video input, which produces no cover MP4.
- Light noise reduction uses RNNoise. If the RNNoise model is unavailable (not downloaded, or the download failed), the chain falls back to `highpass=f=80,afftdn=nf=-25:tn=1`, FFmpeg's built-in spectral denoiser, which needs no download. The log says "falling back to spectral denoising (afftdn)", so a degraded run is visible instead of silently doing almost nothing.
- `arnndn_mix` in `config.json` (default `0.8`, range 0.0–1.0) blends the denoised signal with the original: `1.0` is fully denoised, and lower values keep more of the original voice. There is no control for it in the window; edit the configuration file by hand.
- Long silent stretches are less likely to produce hallucinated subtitle lines such as "thanks for watching", "subtitles by …", or "please like and subscribe": the recognition thresholds are stricter, and segments of 3 seconds or more whose text matches a known hallucination pattern are dropped, with the count written to the log. See [Known limitations](#known-limitations) for what this does not catch.

Defaults: 1080p, large-v3-turbo, auto-detect, light RNNoise, loudness normalization on, and long sentences first off.

## Common combinations

| Goal | What to select |
| --- | --- |
| Subtitles only | Any model except Off; check SRT, VTT, and/or TXT; no cover needed |
| Subtitles from a video | Choose the video file; check SRT, VTT, and/or TXT; set the spoken language to English for English videos; leave both MP4 options unchecked (they are skipped automatically for video input) |
| MP4 with the original audio | Check "MP4 · Original Audio"; choose a cover |
| MP4 with the denoised audio | Set noise reduction to Light or Strong; check "MP4 · Denoised Audio"; choose a cover |
| Everything | Check both MP4 options and at least one subtitle format, and set noise reduction to Light or Strong |

Every combination of the three groups is valid, from any single group up to all three at once (A+B, A+C, B+C, and A+B+C). The only combination that does nothing is a video input with no subtitle format and no noise reduction.

Two settings pay off quickly:

- When a recording is full of names, company names, or jargon, fill in the glossary / prompt. That is where the improvement is most obvious.
- For Chinese interviews and lectures, turn on "Long sentences first" so the transcript is not chopped into fragments.

To preview noise reduction, set it to Light or Strong and leave every other option unchecked. The app then exports only `recording_denoised.wav`, which you can listen to before producing a video. In general, as long as noise reduction is not Off, `recording_denoised.wav` is written regardless of the other options.

## Output files and naming

Output goes to the selected output folder. If no folder is selected, it goes to the folder of the first audio file.

For an input named `recording.mp3`:

| Output | File name |
| --- | --- |
| Subtitles | `recording.srt`, `recording.vtt`, `recording.txt` |
| Video with the original audio | `recording.mp4` |
| Denoised audio | `recording_denoised.wav` (48 kHz, stereo, 16-bit PCM) |
| Video with the denoised audio | `recording_denoised.mp4` |

Existing files are never overwritten. If a name is already taken, ` (1)`, ` (2)`, and so on are appended before the extension.

For a video input such as `lecture.mp4` with SRT and VTT checked, the outputs are `lecture.srt` and `lecture.vtt`, plus `lecture_denoised.wav` when noise reduction is on. No `lecture.mp4` is written, and the original picture is never re-encoded.

Video is encoded as H.264 (libx264) at 1 frame per second, with AAC 192 kbps audio and the `faststart` flag. In 1080p and 720p modes, covers that are not 16:9 are scaled down and padded with black bars; original-size mode keeps the source dimensions, rounded down to even numbers. SRT, VTT, and TXT subtitles are sidecar files; they are not burned into the video.

## Subtitle formats

| Format | File | Characteristics |
| --- | --- | --- |
| SubRip | `.srt` | Numbered cues; milliseconds separated by a comma |
| WebVTT | `.vtt` | Starts with `WEBVTT` and a blank line; milliseconds separated by a period; no cue numbers |
| Plain text | `.txt` | All segments joined into a single line, with a space inserted between Latin words |

All three formats share the same layout rules: 42 display columns per line (a CJK character counts as 2), at most 3 lines per cue, empty segments skipped, and a minimum cue length of 0.2 seconds. Files are UTF-8 without a BOM.

VTT output is deliberately plain: no `STYLE` blocks, no `NOTE` comments, no cue identifiers, and no karaoke timestamps. Any combination of SRT, VTT, and TXT can be produced in one run.

VTT is unchecked by default. It shares the recognition-model switch with SRT and TXT, so it is greyed out when the model is set to Off, and its state is written to the configuration file.

## Interface language

The interface ships in Simplified Chinese, Traditional Chinese, and English. Use the selector in the top-right corner; the change applies immediately and does not restart the app. The first launch starts in Simplified Chinese, and the selection is remembered. Log lines that have already been written keep the language they were printed in and are not retranslated.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- FFmpeg with the `libx264` and `aac` encoders

FFmpeg is not bundled with the application and must be installed separately.

## Installation

### Option 1: run from a clone

```bash
git clone https://github.com/zqd9853572002/Mp3_to_Mp4.git
cd Mp3_to_Mp4
pip install -r requirements.txt
python MP3toMP4.py
```

### Option 2: install as a package

```bash
pip install .
mp3tom4
```

`mp3tom4-gui` starts the same application.

### Option 3: install with optional features

```bash
pip install ".[full]"
```

This adds `sherpa-onnx` for strong GTCRN noise reduction and `imageio-ffmpeg` as an additional FFmpeg source.

### FFmpeg on Windows

```powershell
winget install Gyan.FFmpeg
```

The application searches, in order: the last path saved in the configuration, `ffmpeg.exe` next to the program, `PATH`, winget package directories, common installation paths, and `imageio-ffmpeg`. You can also click **Change** at the top of the window to select `ffmpeg.exe` manually. A build is accepted only if it provides both `libx264` and `aac`; otherwise the application reports which encoder is missing. Installing `imageio-ffmpeg` with pip adds one more fallback source.

## Data and cache

| Data | Location |
| --- | --- |
| Configuration | `%APPDATA%\Mp3ToMp4\config.json` |
| Model cache | `%APPDATA%\Mp3ToMp4\models\` (with `whisper\` and `denoise\` subfolders) |

The configuration file stores the FFmpeg path, the last cover image, the output folder, the resolution, the interface language, and the recognition settings.

Settings added in 5.2.0:

| Key | Meaning |
| --- | --- |
| `asr_initial_prompt` | Glossary / prompt text, at most 800 characters; same as the box in the recognition group |
| `asr_vad_mode` | `standard` (default) or `long`, the state of "Long sentences first" |
| `loudnorm_enabled` | `true` (default) or `false`, the state of "Loudness normalization" |
| `arnndn_mix` | RNNoise blend ratio, `0.8` by default, valid range 0.0–1.0; configuration file only |

The first run with a given recognition model downloads its weights into `models\whisper\`:

| Model | Download size |
| --- | --- |
| large-v3-turbo | 1.55 GB |
| medium | 1.46 GB |
| small | 464 MB |
| base | 141 MB |
| tiny | 75 MB |

The download requires a network connection and can take minutes to tens of minutes. The log reports it before it starts, so an apparently idle first run is usually a download in progress. Models stay on disk between runs, and deleting the folder is safe. The two small noise-reduction models are downloaded into `models\denoise\` on first use.

## Project structure

```text
mp3tom4/
├── config.py       constants, configuration, paths
├── i18n.py         localization framework
├── ffmpeg.py       FFmpeg discovery, filters, muxing
├── denoise.py      noise reduction (RNNoise / GTCRN)
├── asr.py          speech recognition (faster-whisper)
├── subtitle.py     SRT / VTT / TXT generation
├── pipeline.py     job orchestration
├── ui/             interface
└── locale/         translation catalogs
tests/              pytest suite
```

## Development and testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests that invoke a real FFmpeg binary are marked `integration` and can be skipped with `pytest tests/ -m "not integration"`.

## Known limitations

1. **Strong noise reduction loses high frequencies.** GTCRN works on 16 kHz audio, and the result is upsampled to 48 kHz. High-frequency detail is genuinely lost and the output can sound dull. Use Light RNNoise when fidelity matters, and Strong GTCRN when noise removal matters more.
2. **Cancellation is not instantaneous.** FFmpeg-based steps such as noise reduction and muxing stop immediately, but Whisper inference is a blocking call, so cancellation waits for the current segment to finish.
3. **The first transcription is slow.** It includes downloading the model and can take minutes to tens of minutes depending on the network and model size.
4. **Subtitles are sidecar files.** They are not burned into the video picture.
5. **Video input keeps no picture.** A video is only an audio source: its frames are never kept, remuxed, or re-encoded. The two cover MP4 options are therefore skipped for video files: they stay greyed out, do not run even if they were checked, and need no cover image; the checked state is kept for the next audio file. A video with no subtitle format and no noise reduction has nothing left to do, so the app asks for at least one of them.
6. **Only the first audio track is used.** Multi-track videos, such as dual-language releases, cannot pick a track; the second and later tracks are ignored.
7. **A silent video cannot be processed.** A video without an audio track stops with a readable message instead of FFmpeg stderr.
8. **Log history is not retranslated.** Switching the interface language leaves existing log lines in their original language.
9. **Hallucination filtering is only partial.** It is based on text pattern matching and only drops segments of 3 seconds or more whose text matches a known pattern; a hallucination that does not match any pattern is kept. Word-level timestamps stay off, because faster-whisper's `hallucination_silence_threshold` requires them and enabling them would slow recognition noticeably.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for the full text. You may use, modify, and redistribute the software; if you distribute a modified version, it must be released under the same license.

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech recognition
- [GTCRN / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — strong noise reduction
- [RNNoise](https://jmvalin.ca/demos/rnnoise/) — light noise reduction
- [FFmpeg](https://ffmpeg.org/) — decoding, encoding, and muxing
