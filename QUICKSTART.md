# ClipScribe quick start

**English** | [简体中文](QUICKSTART.zh-CN.md) | [繁體中文](QUICKSTART.zh-TW.md)

From a fresh copy of the project to your first subtitle file. The hands-on part takes about five minutes; the first model download can add a few minutes or more, depending on your connection.

[Back to the README](README.md)

## 1. What you need

- Windows 10 or 11.
- Python 3.10 or newer (`pyproject.toml` declares `requires-python = ">=3.10"`). During setup, tick **Add python.exe to PATH**.
- FFmpeg with the `libx264` and `aac` encoders — **required**. A build with `libass` is optional and only needed for burned-in subtitles.
- Free disk space: 75 MB to 1.55 GB for the recognition model you pick, plus room for the output files.
- An internet connection the first time you use a given recognition model (the weights are downloaded once, then cached).

Check your Python:

```bash
python --version
```

## 2. Three steps to install

### Step 1 — Install FFmpeg

```powershell
winget install Gyan.FFmpeg
```

Open a new terminal afterwards so `PATH` picks up the new entry.

Already have FFmpeg but ClipScribe cannot find it? The app probes, in order: the last path saved in the configuration, `ffmpeg.exe` next to the program, `PATH`, winget package directories, common installation paths, and `imageio-ffmpeg`. You can also click **Change** at the top of the window and pick `ffmpeg.exe` by hand. A build is accepted only if it provides both `libx264` and `aac`.

### Step 2 — Install the Python dependencies

From the project folder:

```bash
pip install -r requirements.txt
```

This installs `faster-whisper` and `numpy`. Add the optional extras when you want them:

```bash
pip install ".[full]"
```

`full` adds `sherpa-onnx` (strong GTCRN noise reduction) and `imageio-ffmpeg` (one more FFmpeg source).

### Step 3 — Start the app

```bash
python ClipScribe.py
```

`python -m clipscribe` works too, and after `pip install .` you can use the `clipscribe` or `clipscribe-gui` command.

On first start you should see:

- the welcome line `>>> Welcome to ClipScribe v6.0.0 (audio/video transcription · subtitles · cover-image MP4 · noise reduction).`
- the FFmpeg detection result, including whether `libx264`, `aac`, and `libass` were found;
- one line about the config and model folder (for example "No legacy config folder found").

If FFmpeg was rejected, the log names the missing encoder; fix that before going further.

## 3. Your first subtitle: the full walkthrough

1. **Pick a file.** Click **Choose Audio / Video** and choose one or more files. Audio and video can be mixed; `Ctrl+A` selects everything in the dialog.
2. **Choose a recognition model.** Start with **small**. If it feels slow, drop to `base` or `tiny`; if accuracy matters more than time, use `large-v3-turbo`.
3. **Choose the spoken language.** Pick **English** for English material, **Chinese** for Chinese, or leave **Auto-detect** for mixed speech.
4. **Tick the subtitle formats you want.** SRT for platform uploads, VTT for web players, TXT when you only need plain text. They can be combined.
5. **Press Start.** The progress bar advances per stage. The first run of a model downloads its weights first — watch the log rather than the progress bar.
6. **Collect the output.** Files are written to the output folder; if none is set, next to the first input file. An input named `interview.mp3` produces `interview.srt` (plus `.vtt` / `.txt` if selected).

First-run download sizes: tiny 75 MB, base 141 MB, small 464 MB, medium 1.46 GB, large-v3-turbo 1.55 GB. The weights land in `%APPDATA%\ClipScribe\models\` and are reused on later runs.

## 4. The three most useful recipes

**Recipe 1 — subtitles from a video**

- Select the video file (MP4, WebM, MKV, MOV, or M4V).
- Set the model (for example `small`), the language (for example English), and tick SRT and/or VTT.
- Leave both cover MP4 options unchecked. They are skipped for video input anyway, and the picture is not kept.

**Recipe 2 — a finished video with burned-in subtitles**

- Select the audio file and a cover image (JPG, PNG, BMP, or WEBP).
- Tick **MP4 · Original Audio** and at least one subtitle format.
- Tick **Burn subtitles into the picture**. Loudness normalization stays on by default; that is usually what you want.
- Hard subtitles need FFmpeg with `libass`. If the checkbox is greyed out, see the troubleshooting section.

**Recipe 3 — just clean up a recording**

- Set noise reduction to **Light (RNNoise)** or **Strong (GTCRN)**.
- Leave the recognition model at **Off** and tick no subtitle format or MP4 option.
- You get `recording_denoised.wav` (48 kHz, stereo) and nothing else.

## 5. Four switches that improve accuracy

- **Glossary / prompt** — type names, company names, and jargon here (up to 800 characters). It is passed to Whisper as `initial_prompt` and gives the most visible improvement.
- **Long sentences first** — turn it on when Chinese sentences keep getting chopped into fragments; it relaxes the VAD splitting thresholds.
- **Loudness normalization** — keep it on when clips from different sources vary wildly in volume; it only affects the finished MP4, never the audio sent to recognition.
- **Hallucination suppression** — on by default. It drops segments of 3 seconds or more whose text matches known hallucination patterns and logs how many were removed; shorter bogus lines are not caught.

## 6. Troubleshooting

| Symptom | What to do |
| --- | --- |
| "FFmpeg not found" | Install it with `winget install Gyan.FFmpeg`, open a new terminal, or click **Change** and select `ffmpeg.exe` manually. |
| "Missing libx264" or "missing aac" | Your FFmpeg build lacks a required encoder. Install the Gyan.FFmpeg build (or another full build) and re-detect. |
| The Start button is greyed out | Usually one of three things: no input file selected; no option group enabled at all; or audio input with a cover MP4 option but no cover image. |
| "Burn subtitles" is greyed out | One of four conditions is unmet: no cover MP4 checked; no subtitle format checked; the input is a video; or the current FFmpeg has no libass. |
| Model download stalls or fails | The first use of a model needs a network connection. Sizes range from 75 MB to 1.55 GB. Once the network is back, run the same job again; files already downloaded stay on disk and are reused. |
| Recognition is inaccurate | Fill in the glossary / prompt, move up to a larger model, and turn on long sentences first for Chinese material. |
| The video picture is gone | By design: video is only an audio source. Only the first audio track is used, and the frames are never kept. |
| Where did my 5.x settings and models go? | They were renamed to `%APPDATA%\ClipScribe` on first start. The startup log confirms which case applied; nothing is re-downloaded. |
| An output file already exists | Nothing is overwritten. ` (1)`, ` (2)`, and so on are appended before the extension. |

## 7. Next steps

- Full feature reference, output naming, subtitle layout rules, and known limitations: [README.md](README.md).
- Version history: [CHANGELOG.md](CHANGELOG.md).
- Other languages: [简体中文](QUICKSTART.zh-CN.md) · [繁體中文](QUICKSTART.zh-TW.md).
