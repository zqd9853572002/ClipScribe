# ClipScribe

**English** | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

![CI](https://github.com/zqd9853572002/ClipScribe/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-GPL--3.0-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

> **New here?** Start with the [Quick start](QUICKSTART.md) — from zero to your first subtitle in about five minutes.

ClipScribe is a local, offline Windows desktop tool that turns audio and video into subtitles (SRT, VTT, TXT) and cover-image MP4 videos, with optional neural noise reduction and burned-in hard subtitles. Everything runs on your own machine; the only network access is the one-time model download.

![Application window](docs/screenshots/en.png)

> The screenshots show version 5.x. In 6.0.0 the product was renamed to ClipScribe; the interface layout is unchanged and only the window title and welcome line differ.

## Contents

- [What it does](#what-it-does)
- [Execution model](#execution-model)
- [Common recipes](#common-recipes)
- [Output files and naming](#output-files-and-naming)
- [Subtitle formats](#subtitle-formats)
- [Interface language](#interface-language)
- [Upgrading from 5.x](#upgrading-from-5x)
- [Requirements](#requirements)
- [Installation](#installation)
- [Data and cache](#data-and-cache)
- [Project structure](#project-structure)
- [Development and testing](#development-and-testing)
- [Known limitations](#known-limitations)
- [License](#license)
- [Credits](#credits)

## What it does

| Area | Details |
| --- | --- |
| Audio input | 17 formats: MP3, M4A, M4B, AAC, WAV, FLAC, OGG, OGA, OPUS, WMA, AIFF, AIF, APE, WV, AMR, AC3, DTS |
| Video input | 5 containers: MP4, WebM, MKV, MOV, M4V. Only the first audio track is extracted; the picture is not kept |
| A · Noise reduction | FFmpeg RNNoise (`arnndn`, blend ratio configurable) or sherpa-onnx GTCRN. Falls back to FFmpeg spectral denoising (`afftdn`) when the RNNoise model is missing |
| B · Speech recognition → subtitles | faster-whisper on CPU (int8); models tiny, base, small, medium, large-v3-turbo; languages auto / Chinese / English; SRT, VTT, and TXT output in any combination |
| C · Cover-image MP4 | Still cover + audio track, 1 fps H.264 + AAC 192 kbps; optional loudness normalization (−16 LUFS, on by default); optional burned-in hard subtitles |
| Extras | Glossary / prompt (`initial_prompt`, up to 800 characters), long-sentences-first VAD mode, hallucination suppression, three-language interface |

The three groups are independent: run any one of them, any two, or all three in a single pass.

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
| | Burn subtitles into the picture (hard subs) | Off by default; needs a cover MP4 output, a subtitle format, an audio input, and FFmpeg with libass |

- Noise reduction runs at most once per file; subtitles and the denoised video reuse that result. Whenever the noise-reduction group is not Off, `{name}_denoised.wav` is always written, even if no subtitle or video output uses it.
- Any combination of the three groups can run: each group on its own, or A+B, A+C, B+C, and A+B+C. The only combination that cannot run is a video input with nothing checked except a cover MP4 option; the app then asks for at least one subtitle format or noise reduction.
- A cover image is required only for audio input with a cover MP4 option selected. Video input never needs a cover.
- The denoised-video option requires noise reduction to be on; when noise reduction is Off, that option is ignored.
- For video input, both cover MP4 options are skipped: they stay greyed out, they do not run even if they were checked earlier, and no cover image is requested. The app reports "Cover MP4 is skipped for this run (video input only provides its audio track)". Their checked state is kept and restored when you go back to an audio file.
- Accepted audio formats are the ones FFmpeg can decode, including MP3, M4A, M4B, AAC, WAV, FLAC, OGG, OGA, OPUS, WMA, AIFF, AIF, APE, WV, AMR, AC3, and DTS.
- Accepted video formats are MP4, WebM, MKV, MOV, and M4V. Only the first audio track is extracted (`-vn`, first audio stream) and converted to 16 kHz mono WAV before recognition, so a multi-track video cannot switch tracks.
- A video with no audio track stops with a readable message ("The input has no usable audio track…") instead of raw FFmpeg stderr.
- The glossary / prompt is handed to Whisper as `initial_prompt`. It mainly helps with names, company names, and domain jargon, and also steadies punctuation. Text longer than 800 characters is truncated, and the log says so.
- Long sentences first switches the VAD settings from standard (`min_silence_duration_ms=400`, `speech_pad_ms=200`) to long (`700`, `300`, and `threshold=0.4`), so a long Chinese sentence is less likely to be split into pieces. It is off by default.
- Loudness normalization appends `loudnorm=I=-16:TP=-1.5:LRA=11` to the audio chain of the finished MP4, keeping clips from different sources at a similar level. It is applied only to video output, never to the audio sent to recognition, and it is greyed out for video input, which produces no cover MP4.
- Burn subtitles into the picture renders the SRT directly into the frames with FFmpeg's `subtitles` filter (libass), so the MP4 itself shows the text. It is off by default, and it is available only when all four conditions hold: at least one cover MP4 output is checked, at least one subtitle format is checked, the input is audio rather than video, and the current FFmpeg includes libass. Otherwise the checkbox is greyed out with the exact reason: "Video input produces no cover MP4, so hard subtitles do not apply", "No cover MP4 selected, so hard subtitles cannot be burned", "No subtitle format selected, so hard subtitles cannot be burned", or "This FFmpeg lacks libass, so hard subtitles cannot be burned". Sidecar subtitle files are still written, so burn-in and sidecar output never conflict.
- Light noise reduction uses RNNoise. If the RNNoise model is unavailable (not downloaded, or the download failed), the chain falls back to `highpass=f=80,afftdn=nf=-25:tn=1`, FFmpeg's built-in spectral denoiser, which needs no download. The log says "falling back to spectral denoising (afftdn)", so a degraded run is visible instead of silently doing almost nothing.
- `arnndn_mix` in `config.json` (default `0.8`, range 0.0–1.0) blends the denoised signal with the original: `1.0` is fully denoised, and lower values keep more of the original voice. There is no control for it in the window; edit the configuration file by hand.
- Long silent stretches are less likely to produce hallucinated subtitle lines such as "thanks for watching", "subtitles by …", or "please like and subscribe": the recognition thresholds are stricter (`no_speech_threshold` 0.5, `log_prob_threshold` −1.0), and segments of 3 seconds or more whose text matches a known hallucination pattern are dropped, with the count written to the log. See [Known limitations](#known-limitations) for what this does not catch.

Defaults: 1080p, large-v3-turbo, auto-detect, light RNNoise, loudness normalization on, long sentences first off, and burn subtitles off.

## Common recipes

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

Video is encoded as H.264 (libx264) at 1 frame per second, with AAC 192 kbps audio and the `faststart` flag. In 1080p and 720p modes, covers that are not 16:9 are scaled down and padded with black bars; original-size mode keeps the source dimensions, rounded down to even numbers. SRT, VTT, and TXT subtitle files are always written as sidecar files. When burn-in is on, the same SRT is also rendered into the frames, so one run can produce both a hard-subtitle MP4 and the sidecar files. Burn-in adds no processing step, so the progress bar is unchanged.

## Subtitle formats

| Format | File | Characteristics |
| --- | --- | --- |
| SubRip | `.srt` | Numbered cues; milliseconds separated by a comma |
| WebVTT | `.vtt` | Starts with `WEBVTT` and a blank line; milliseconds separated by a period; no cue numbers |
| Plain text | `.txt` | All segments joined into a single line, with a space inserted between Latin words |

All three formats share the same layout rules: 42 display columns per line (a CJK character counts as 2), at most 3 lines per cue, empty segments skipped, and a minimum cue length of 0.2 seconds. Files are UTF-8 without a BOM.

VTT output is deliberately plain: no `STYLE` blocks, no `NOTE` comments, no cue identifiers, and no karaoke timestamps. Any combination of SRT, VTT, and TXT can be produced in one run.

VTT is unchecked by default. It shares the recognition-model switch with SRT and TXT, so it is greyed out when the model is set to Off, and its state is written to the configuration file.

**Sidecar vs. burned-in subtitles.** SRT, VTT, and TXT are sidecar files: the player or platform reads them separately and viewers can switch them on and off. Burned-in subtitles ("hard subs") are painted into the picture by FFmpeg's `subtitles` filter (libass) and cannot be turned off. Use sidecar files for Bilibili and YouTube uploads, where captions are stored separately and can carry multiple languages; use burned-in subtitles for WeChat and Douyin, where the player has no caption track and the text must be visible in the picture itself. Checking burn-in does not stop the sidecar files from being written.

Burn-in reuses the SRT file when SRT is checked. If only VTT and/or TXT is selected, the app generates a temporary SRT for rendering and does not leave it in the output folder. The font size is about 3% of the output height (clamped to 16–48), the margin about 4% (clamped to 10–80), with a 2 px outline and no shadow. Chinese fonts are probed in the order `Microsoft YaHei` → `Noto Sans CJK SC`; if neither exists, libass picks a fallback and the log warns that glyphs may be missing. Chinese and space-containing paths on Windows work normally (the implementation uses a temporary ASCII directory and a relative filter path to avoid escaping problems).

## Interface language

The interface ships in Simplified Chinese, Traditional Chinese, and English. Use the selector in the top-right corner; the change applies immediately and does not restart the app. The first launch starts in Simplified Chinese, and the selection is remembered. Log lines that have already been written keep the language they were printed in and are not retranslated.

## Upgrading from 5.x

Version 6.0.0 renames the project:

| Item | 5.x | 6.0.0 |
| --- | --- | --- |
| Product name | MP3 to MP4 | **ClipScribe** |
| Launcher script | `MP3toMP4.py` | `ClipScribe.py` |
| Python package | `mp3tom4/` | `clipscribe/` |
| Console commands | `mp3tom4`, `mp3tom4-gui` | `clipscribe`, `clipscribe-gui` |
| Config and model folder | `%APPDATA%\Mp3ToMp4` | `%APPDATA%\ClipScribe` |

**Your settings and downloaded models carry over automatically.** On first start, 6.0.0 renames `%APPDATA%\Mp3ToMp4` to `%APPDATA%\ClipScribe` as a whole directory. Nothing is copied, and already-downloaded models are not downloaded again.

The migration has three levels of fallback and never crashes the app:

1. A direct rename (`os.replace`) — instant on the same drive.
2. If the rename fails, a move (`shutil.move`) — used when the two paths sit on different drives.
3. If both fail, migration is abandoned: the app keeps using the old folder, logs a warning with the reason, and starts normally.

Other rules:

- If `%APPDATA%\ClipScribe` already exists, nothing is migrated, overwritten, or merged. The new folder wins, and the old folder is left untouched.
- The old folder is only a migration source. In normal use it is never read or written again.
- The startup log always prints one line about the config folder: migrated / using the new folder / no legacy folder found / migration failed and the old folder is still in use.

**If you need to go back to 5.x.** The old version looks only at `%APPDATA%\Mp3ToMp4`, which no longer exists, so it creates an empty folder and downloads the recognition model again. To avoid re-downloading, copy `%APPDATA%\ClipScribe` back to `%APPDATA%\Mp3ToMp4` before running 5.x. Copying does not disturb the 6.0.0 folder, and 6.0.0 will not touch the restored old folder on the next start.

**Command changes.** `python MP3toMP4.py` becomes `python ClipScribe.py`; the module form `python -m clipscribe` and the installed commands `clipscribe` / `clipscribe-gui` also work. Any script, shortcut, or scheduled task that referenced the old script name or the `mp3tom4` package must be updated.

The GitHub repository is being renamed to `ClipScribe` at <https://github.com/zqd9853572002/ClipScribe>; old links redirect to the new address.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- FFmpeg with the `libx264` and `aac` encoders
- Optional: an FFmpeg build with `libass`, needed only for burned-in subtitles

FFmpeg is not bundled with the application and must be installed separately.

`libx264` and `aac` are required: a build that lacks either one is rejected. `libass` is optional: without it every other feature works normally, only burn-in is unavailable, and the startup log says "subtitle burn-in is unavailable, everything else works normally". To check your own build, run `ffmpeg -filters` and look for the `subtitles` filter (a line such as `.. subtitles  V->V  Render text...`).

Disk space: leave room for the recognition model you plan to use (75 MB to 1.55 GB, see [Data and cache](#data-and-cache)) plus the output files.

## Installation

### Option 1: run from a clone

```bash
git clone https://github.com/zqd9853572002/ClipScribe.git
cd ClipScribe
pip install -r requirements.txt
python ClipScribe.py
```

### Option 2: install as a package

```bash
pip install .
clipscribe
```

`clipscribe-gui` starts the same application. `python -m clipscribe` works from a checkout without installing.

### Option 3: install with optional features

```bash
pip install ".[full]"
```

This adds `sherpa-onnx` for strong GTCRN noise reduction and `imageio-ffmpeg` as an additional FFmpeg source.

### FFmpeg on Windows

```powershell
winget install Gyan.FFmpeg
```

The application searches, in order: the last path saved in the configuration, `ffmpeg.exe` next to the program, `PATH`, winget package directories, common installation paths, and `imageio-ffmpeg`. You can also click **Change** at the top of the window to select `ffmpeg.exe` manually. A build is accepted only if it provides both `libx264` and `aac`; otherwise the application reports which encoder is missing. libass is not part of that check: a build without it still runs, but burn-in stays greyed out. To confirm libass support, check that `ffmpeg -filters` lists `subtitles`. Installing `imageio-ffmpeg` with pip adds one more fallback source.

## Data and cache

| Data | Location |
| --- | --- |
| Configuration | `%APPDATA%\ClipScribe\config.json` |
| Model cache | `%APPDATA%\ClipScribe\models\` (with `whisper\` and `denoise\` subfolders) |

The configuration file stores the FFmpeg path, the last cover image, the output folder, the resolution, the interface language, and the recognition settings.

Settings added in 5.2.0:

| Key | Meaning |
| --- | --- |
| `asr_initial_prompt` | Glossary / prompt text, at most 800 characters; same as the box in the recognition group |
| `asr_vad_mode` | `standard` (default) or `long`, the state of "Long sentences first" |
| `loudnorm_enabled` | `true` (default) or `false`, the state of "Loudness normalization" |
| `arnndn_mix` | RNNoise blend ratio, `0.8` by default, valid range 0.0–1.0; configuration file only |

Settings added in 5.3.0:

| Key | Meaning |
| --- | --- |
| `burn_subtitles` | `false` (default) or `true`, the state of "Burn subtitles into the picture" |

6.0.0 adds no new keys: the existing configuration is reused as-is after the folder migration.

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
ClipScribe.py       launcher (python ClipScribe.py)
clipscribe/
├── __main__.py     python -m clipscribe
├── app.py          startup: logging, folder migration, window
├── config.py       constants, configuration, paths, migration
├── i18n.py         localization framework
├── ffmpeg.py       FFmpeg discovery, filters, muxing
├── denoise.py      noise reduction (RNNoise / GTCRN)
├── asr.py          speech recognition (faster-whisper)
├── subtitle.py     SRT / VTT / TXT generation
├── pipeline.py     job orchestration
├── ui/             interface
└── locale/         translation catalogs
tests/              pytest suite (303 tests)
docs/screenshots/   interface screenshots
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
4. **Subtitles are sidecar files by default.** Burn-in is opt-in, requires a cover MP4 output and FFmpeg with libass, and applies only to audio input. When burn-in is off, subtitles are never rendered into the picture.
5. **Video input keeps no picture.** A video is only an audio source: its frames are never kept, remuxed, or re-encoded. The two cover MP4 options are therefore skipped for video files: they stay greyed out, do not run even if they were checked, and need no cover image; the checked state is kept for the next audio file. A video with no subtitle format and no noise reduction has nothing left to do, so the app asks for at least one of them.
6. **Only the first audio track is used.** Multi-track videos, such as dual-language releases, cannot pick a track; the second and later tracks are ignored.
7. **A silent video cannot be processed.** A video without an audio track stops with a readable message instead of FFmpeg stderr.
8. **Log history is not retranslated.** Switching the interface language leaves existing log lines in their original language.
9. **Hallucination filtering is only partial.** It is based on text pattern matching and only drops segments of 3 seconds or more whose text matches a known pattern; a hallucination that does not match any pattern is kept. Word-level timestamps stay off, because faster-whisper's `hallucination_silence_threshold` requires them and enabling them would slow recognition noticeably.
10. **Font size on original-size output uses a 1080-height baseline.** The burn-in style is computed from the output height, so a 4K source gets slightly smaller text and a tiny image gets slightly larger text. Both stay within the 16–48 range, so the text is never unreadable.

ClipScribe does not translate, does not separate speakers, does not use the GPU, does not accept drag-and-drop, and does not include a subtitle editor. See [What it does](#what-it-does) for the complete feature list.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for the full text. You may use, modify, and redistribute the software; if you distribute a modified version, it must be released under the same license.

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech recognition
- [GTCRN / sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) — strong noise reduction
- [RNNoise](https://jmvalin.ca/demos/rnnoise/) — light noise reduction
- [FFmpeg](https://ffmpeg.org/) — decoding, encoding, and muxing
