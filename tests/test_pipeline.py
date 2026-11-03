# -*- coding: utf-8 -*-
"""pipeline 模块：JobPlan 推导（六种组合 + only_denoise）与五条回归链路。"""

import inspect
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from mp3tom4 import pipeline as pipeline_mod
from mp3tom4.ffmpeg import probe_duration
from mp3tom4.pipeline import Pipeline, build_plan, build_steps, option_flags

BASE = dict(
    audio_files=["/tmp/a.mp3"],
    output_dir="/tmp/out",
    image_path="/tmp/cover.png",
    size_mode="720p",
    model_code="tiny",
    denoise_code="off",
    lang_code="auto",
    srt=False,
    txt=False,
    mux_original=False,
    mux_denoised=False,
)


def make_plan(**overrides):
    kwargs = dict(BASE)
    kwargs.update(overrides)
    return build_plan(**kwargs)


# ==================== JobPlan 推导（纯逻辑）====================
def test_plan_srt_only():
    plan = make_plan(srt=True)
    assert plan.need_stt is True
    assert plan.need_denoise is False
    assert plan.only_denoise is False
    assert plan.mux_original is False and plan.mux_denoised is False
    assert plan.model_name == "tiny"
    assert plan.language is None


def test_plan_txt_only():
    plan = make_plan(txt=True)
    assert plan.need_stt is True
    assert plan.need_denoise is False
    assert plan.only_denoise is False
    assert plan.srt is False and plan.txt is True


def test_plan_vtt_only():
    """只勾 VTT 也必须触发识别。"""
    plan = make_plan(vtt=True)
    assert plan.need_stt is True
    assert plan.vtt is True
    assert plan.srt is False and plan.txt is False
    assert plan.need_denoise is False
    assert plan.only_denoise is False


def test_plan_vtt_defaults_off():
    """未显式传入 vtt 时（旧调用方）保持关闭，不改变既有行为。"""
    assert make_plan(srt=True).vtt is False


def test_plan_vtt_with_srt():
    plan = make_plan(srt=True, vtt=True)
    assert plan.need_stt is True
    assert plan.srt is True and plan.vtt is True


def test_plan_srt_and_txt():
    plan = make_plan(srt=True, txt=True)
    assert plan.need_stt is True
    assert plan.srt is True and plan.txt is True
    assert plan.need_denoise is False


def test_plan_original_mp4_only():
    plan = make_plan(model_code="off", mux_original=True)
    assert plan.need_stt is False
    assert plan.need_denoise is False
    assert plan.only_denoise is False
    assert plan.mux_original is True
    assert plan.model_name is None


def test_plan_denoised_mp4_only():
    plan = make_plan(model_code="off", denoise_code="arnndn", mux_denoised=True)
    assert plan.need_denoise is True
    assert plan.mux_denoised is True
    assert plan.need_stt is False
    assert plan.only_denoise is False
    assert plan.denoise_mode == "arnndn"


def test_plan_everything():
    plan = make_plan(srt=True, txt=True, denoise_code="arnndn",
                     mux_original=True, mux_denoised=True)
    assert plan.need_stt is True
    assert plan.need_denoise is True
    assert plan.only_denoise is False
    assert plan.mux_original is True and plan.mux_denoised is True


def test_plan_only_denoise_scenario():
    plan = make_plan(model_code="off", denoise_code="arnndn")
    assert plan.only_denoise is True
    assert plan.need_denoise is True
    assert plan.need_stt is False
    assert plan.mux_original is False and plan.mux_denoised is False


def test_plan_denoise_off_ignores_denoised_mux():
    plan = make_plan(model_code="off", denoise_code="off", mux_denoised=True)
    assert plan.mux_denoised is False
    assert plan.need_denoise is False
    assert plan.only_denoise is False


def test_plan_stt_off_with_subtitle_toggles():
    plan = make_plan(model_code="off", srt=True, txt=True)
    assert plan.need_stt is False
    assert plan.need_denoise is False
    assert plan.only_denoise is False


def test_plan_language_mapping():
    assert make_plan(lang_code="auto").language is None
    assert make_plan(lang_code="zh").language == "zh"
    assert make_plan(lang_code="en").language == "en"


def test_plan_size_mode_mapping():
    # 内部值直通
    assert make_plan(size_mode="1080p").size_mode == "1080p"
    assert make_plan(size_mode="orig").size_mode == "orig"
    # 旧版显示文案仍可识别（向后兼容）
    assert make_plan(size_mode="720p (1280x720)").size_mode == "720p"
    assert make_plan(size_mode="原图尺寸（仅偶数修正）").size_mode == "orig"
    # 无法识别时回退默认值
    assert make_plan(size_mode="不存在的模式").size_mode == "1080p"


def test_plan_keeps_ffmpeg_path():
    assert make_plan(ffmpeg_path="/x/ffmpeg.exe").ffmpeg_path == "/x/ffmpeg.exe"


def test_plan_quality_fields_defaults_preserve_old_behavior():
    """旧调用方不传新参数时：无提示词、standard VAD、响度标准化默认开。"""
    plan = make_plan(srt=True)
    assert plan.initial_prompt == ""
    assert plan.vad_mode == "standard"
    assert plan.loudnorm_enabled is True


def test_plan_passes_quality_fields():
    plan = make_plan(srt=True, initial_prompt="  Acme, 张伟  ",
                     vad_mode="long", loudnorm_enabled=False)
    assert plan.initial_prompt == "Acme, 张伟"
    assert plan.vad_mode == "long"
    assert plan.loudnorm_enabled is False


def test_plan_rejects_unknown_vad_mode():
    assert make_plan(vad_mode="不存在的模式").vad_mode == "standard"


def test_do_stt_forwards_prompt_and_vad(monkeypatch, tmp_path):
    """非默认的识别质量控制参数必须传到 transcribe_audio。"""
    captured = {}

    def fake_prepare(ffmpeg, src, mode, workdir, log=None):
        return "input.wav"

    def fake_transcribe(audio_path, model_name, language, duration,
                        on_progress, should_stop, log=None, **kwargs):
        captured.update(kwargs)
        return [{"start": 0.0, "end": 1.0, "text": "hello"}], SimpleNamespace(
            language="en", language_probability=0.9)

    monkeypatch.setattr(pipeline_mod, "prepare_asr_audio", fake_prepare)
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", fake_transcribe)

    plan = make_plan(srt=True, initial_prompt="Acme", vad_mode="long")
    plan.output_dir = str(tmp_path)
    Pipeline(plan)._do_stt("/tmp/a.mp3", "stem", 1.0, 0.0, 100.0,
                           denoise_mode="off", already_denoised=False)

    assert captured["initial_prompt"] == "Acme"
    assert captured["vad_mode"] == "long"


def test_do_stt_filters_hallucination_segments(monkeypatch, tmp_path):
    """超长 + 命中幻听模式的片段不得写进字幕，正常短句保留。"""

    def fake_prepare(ffmpeg, src, mode, workdir, log=None):
        return "input.wav"

    def fake_transcribe(audio_path, model_name, language, duration,
                        on_progress, should_stop, log=None, **kwargs):
        return [
            {"start": 10.0, "end": 14.0, "text": "谢谢观看"},
            {"start": 14.0, "end": 15.0, "text": "真正的内容"},
        ], SimpleNamespace(language="zh", language_probability=0.9)

    monkeypatch.setattr(pipeline_mod, "prepare_asr_audio", fake_prepare)
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", fake_transcribe)

    plan = make_plan(srt=True)
    plan.output_dir = str(tmp_path)
    Pipeline(plan)._do_stt("/tmp/a.mp3", "stem", 20.0, 0.0, 100.0,
                           denoise_mode="off", already_denoised=False)

    content = (tmp_path / "stem.srt").read_text(encoding="utf-8")
    assert "真正的内容" in content
    assert "谢谢观看" not in content


def test_do_stt_uses_denoise_mode_from_plan(monkeypatch):
    """识别前的降噪模式必须来自任务计划，而不是硬编码的 "off"。"""
    captured = {}

    def fake_prepare(ffmpeg, src, mode, workdir, log=None):
        captured["mode"] = mode
        return ""  # 空串让 _do_stt 立即走「预处理失败」分支，避免真正转写

    monkeypatch.setattr(pipeline_mod, "prepare_asr_audio", fake_prepare)
    plan = make_plan(srt=True, denoise_code="gtcrn")
    pipeline = Pipeline(plan)

    assert pipeline._do_stt("/tmp/a.mp3", "stem", 0.0, 0.0, 100.0,
                            denoise_mode=plan.denoise_mode,
                            already_denoised=False) is False
    assert captured["mode"] == "gtcrn"

    # 源音频已经是降噪产物时不得重复降噪
    captured.clear()
    pipeline._do_stt("/tmp/a_denoised.wav", "stem", 0.0, 0.0, 100.0,
                     denoise_mode=plan.denoise_mode,
                     already_denoised=True)
    assert captured["mode"] == "off"

    # 计划本身关闭降噪时同样透传 "off"
    captured.clear()
    off_plan = make_plan(srt=True, denoise_code="off")
    Pipeline(off_plan)._do_stt("/tmp/a.mp3", "stem", 0.0, 0.0, 100.0,
                               denoise_mode=off_plan.denoise_mode,
                               already_denoised=False)
    assert captured["mode"] == "off"


@pytest.mark.parametrize("overrides", [
    {"srt": True},
    {"txt": True},
    {"srt": True, "txt": True},
    {"vtt": True},
    {"srt": True, "vtt": True},
    {"model_code": "off", "mux_original": True},
    {"model_code": "off", "denoise_code": "arnndn", "mux_denoised": True},
    {"srt": True, "txt": True, "denoise_code": "arnndn",
     "mux_original": True, "mux_denoised": True},
    {"model_code": "off", "denoise_code": "arnndn"},
    {"model_code": "off", "denoise_code": "arnndn", "srt": True},
])
def test_option_flags_matches_plan(overrides):
    plan = make_plan(**overrides)
    flags = option_flags(
        overrides.get("model_code", BASE["model_code"]),
        overrides.get("denoise_code", BASE["denoise_code"]),
        overrides.get("srt", False),
        overrides.get("txt", False),
        overrides.get("mux_original", False),
        overrides.get("mux_denoised", False),
        overrides.get("vtt", False),
    )
    assert flags["need_stt"] == plan.need_stt
    assert flags["denoise_on"] == (plan.denoise_mode is not None)
    assert flags["mux_original"] == plan.mux_original
    assert flags["mux_denoised"] == plan.mux_denoised
    assert flags["only_denoise"] == plan.only_denoise


def test_build_steps_dynamic_weights():
    plan = make_plan(srt=True, denoise_code="arnndn",
                     mux_original=True, mux_denoised=True)
    steps = build_steps(plan)
    assert [name for name, _a, _b in steps] == [
        pipeline_mod.STEP_DENOISE,
        pipeline_mod.STEP_STT,
        pipeline_mod.STEP_MUX_ORIGINAL,
        pipeline_mod.STEP_MUX_DENOISE,
    ]
    assert steps[0][1] == 0.0
    assert steps[-1][2] == pytest.approx(100.0)
    for current, following in zip(steps, steps[1:]):
        assert current[2] == pytest.approx(following[1])


def test_build_steps_empty_plan():
    assert build_steps(make_plan(model_code="off", denoise_code="off")) == []


def test_pipeline_has_no_ui_dependency():
    """依赖方向守卫：pipeline 不得 import 任何 ui 模块。"""
    source = inspect.getsource(pipeline_mod)
    assert "from .ui" not in source
    assert "from ..ui" not in source
    assert "import tkinter" not in source


def test_subtitle_is_pure_module():
    from mp3tom4 import subtitle as subtitle_mod

    source = inspect.getsource(subtitle_mod)
    assert "from .config" not in source
    assert "from .ffmpeg" not in source
    assert "tkinter" not in source


# ==================== 五条回归链路（真实 ffmpeg）====================
class Recorder:
    def __init__(self):
        self.logs = []
        self.progress = []
        self.stages = []
        self.done = 0

    def log(self, text, is_error=False):
        self.logs.append((text, is_error))

    def set_progress(self, value):
        self.progress.append(value)

    def set_stage(self, text):
        self.stages.append(text)

    def on_done(self):
        self.done += 1


def run_pipeline(plan):
    rec = Recorder()
    Pipeline(
        plan,
        log=rec.log,
        set_progress=rec.set_progress,
        set_stage=rec.set_stage,
        should_stop=lambda: False,
        on_proc=lambda proc: None,
        on_done=rec.on_done,
    ).run()
    return rec


def _fake_transcribe(audio_path, model_name, language, duration,
                     on_progress, should_stop, log=None):
    """替身：避免测试加载 Whisper 权重，但保留真实解码/写盘链路。"""
    if on_progress:
        on_progress(50.0)
    segments = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    return segments, SimpleNamespace(language="en", language_probability=0.98)


def _out_dir(tmp_path):
    path = tmp_path / "out"
    path.mkdir()
    return path


@pytest.mark.integration
def test_flow_1_txt_only(monkeypatch, ffmpeg_path, sine_audio, tmp_path):
    """链路 1：只勾 TXT → need_stt=True，只产出 .txt，不产生视频。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="tiny", denoise_code="off",
        lang_code="auto", srt=False, txt=True,
        mux_original=False, mux_denoised=False, ffmpeg_path=ffmpeg_path)
    assert plan.need_stt is True

    rec = run_pipeline(plan)

    stem = Path(sine_audio).stem
    txt_path = out_dir / f"{stem}.txt"
    assert txt_path.is_file()
    assert txt_path.read_text(encoding="utf-8") == "hello world\n"
    assert not list(out_dir.glob("*.mp4"))
    assert not list(out_dir.glob("*.srt"))
    assert rec.done == 1

    # 重名再跑一次 → 自动加序号，不覆盖
    run_pipeline(plan)
    assert (out_dir / f"{stem} (1).txt").is_file()
    assert txt_path.read_text(encoding="utf-8") == "hello world\n"


@pytest.mark.integration
def test_flow_2_original_mp4(ffmpeg_path, sine_audio, black_png, tmp_path):
    """链路 2：只勾原声 MP4 → 产出 <stem>.mp4，时长约 3 秒。"""
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path=black_png,
        size_mode="720p", model_code="off", denoise_code="off",
        lang_code="auto", srt=False, txt=False,
        mux_original=True, mux_denoised=False, ffmpeg_path=ffmpeg_path)
    assert plan.need_denoise is False and plan.need_stt is False

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    mp4 = out_dir / f"{stem}.mp4"
    assert mp4.is_file() and mp4.stat().st_size > 0
    assert 2.5 <= probe_duration(ffmpeg_path, str(mp4)) <= 3.6


@pytest.mark.integration
def test_flow_3_denoise_and_denoised_mp4(ffmpeg_path, sine_audio, black_png,
                                        denoise_model, tmp_path):
    """链路 3：降噪 + 降噪 MP4 → 48kHz/2ch WAV + 降噪配图 MP4。"""
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path=black_png,
        size_mode="720p", model_code="off", denoise_code="arnndn",
        lang_code="auto", srt=False, txt=False,
        mux_original=False, mux_denoised=True, ffmpeg_path=ffmpeg_path)
    assert plan.need_denoise is True

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    wav_path = out_dir / f"{stem}_denoised.wav"
    assert wav_path.is_file()
    with wave.open(str(wav_path), "rb") as handle:
        assert handle.getframerate() == 48000
        assert handle.getnchannels() == 2
        assert handle.getsampwidth() == 2

    mp4 = out_dir / f"{stem}_denoised.mp4"
    assert mp4.is_file() and mp4.stat().st_size > 0
    assert 2.5 <= probe_duration(ffmpeg_path, str(mp4)) <= 3.6


@pytest.mark.integration
def test_flow_4_both_mp4(ffmpeg_path, sine_audio, black_png, denoise_model, tmp_path):
    """链路 4：两个 MP4 同时勾 → 两个文件都在，互不覆盖。"""
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path=black_png,
        size_mode="720p", model_code="off", denoise_code="arnndn",
        lang_code="auto", srt=False, txt=False,
        mux_original=True, mux_denoised=True, ffmpeg_path=ffmpeg_path)

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    original = out_dir / f"{stem}.mp4"
    denoised = out_dir / f"{stem}_denoised.mp4"
    assert original.is_file() and denoised.is_file()
    assert original.stat().st_size > 0 and denoised.stat().st_size > 0
    assert original.name != denoised.name


@pytest.mark.integration
def test_flow_5_only_denoise(ffmpeg_path, sine_audio, denoise_model, tmp_path):
    """链路 5：只开降噪 → 只产出 <stem>_denoised.wav。"""
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="off", denoise_code="arnndn",
        lang_code="auto", srt=False, txt=False,
        mux_original=False, mux_denoised=False, ffmpeg_path=ffmpeg_path)
    assert plan.only_denoise is True

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    assert sorted(path.name for path in out_dir.iterdir()) == [f"{stem}_denoised.wav"]


@pytest.mark.integration
def test_flow_6_vtt_only(monkeypatch, ffmpeg_path, sine_audio, tmp_path):
    """链路 6：只勾 VTT → 只产出 .vtt（无 SRT / TXT / MP4）。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="tiny", denoise_code="off",
        lang_code="auto", srt=False, txt=False, vtt=True,
        mux_original=False, mux_denoised=False, ffmpeg_path=ffmpeg_path)
    assert plan.need_stt is True

    rec = run_pipeline(plan)

    stem = Path(sine_audio).stem
    vtt_path = out_dir / f"{stem}.vtt"
    assert vtt_path.is_file()
    content = vtt_path.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:01.000" in content
    assert not list(out_dir.glob("*.srt"))
    assert not list(out_dir.glob("*.txt"))
    assert not list(out_dir.glob("*.mp4"))
    # 落盘后有独立日志行（log.vtt_saved）
    assert any(".vtt" in text and "VTT" in text for text, _err in rec.logs)
    assert rec.done == 1


@pytest.mark.integration
def test_flow_7_vtt_and_srt(monkeypatch, ffmpeg_path, sine_audio, tmp_path):
    """链路 7：VTT + SRT 同时勾选 → 两个文件都在，内容各自合法。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="tiny", denoise_code="off",
        lang_code="auto", srt=True, txt=False, vtt=True,
        mux_original=False, mux_denoised=False, ffmpeg_path=ffmpeg_path)

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    srt_path = out_dir / f"{stem}.srt"
    vtt_path = out_dir / f"{stem}.vtt"
    assert srt_path.is_file() and vtt_path.is_file()
    assert srt_path.read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> ")
    assert vtt_path.read_text(encoding="utf-8").startswith("WEBVTT\n")
    assert not list(out_dir.glob("*.mp4"))


@pytest.mark.integration
def test_flow_8_video_input_to_vtt(monkeypatch, ffmpeg_path, sine_video, tmp_path):
    """链路 8：mp4 输入 → 只提取音轨做识别 → 写出 .vtt，且不产生视频。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_video], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="tiny", denoise_code="off",
        lang_code="auto", srt=False, txt=False, vtt=True,
        mux_original=False, mux_denoised=False, ffmpeg_path=ffmpeg_path)

    run_pipeline(plan)

    stem = Path(sine_video).stem
    assert (out_dir / f"{stem}.vtt").is_file()
    assert not list(out_dir.glob("*.mp4"))
    assert not [name for name in out_dir.iterdir() if name.name != f"{stem}.vtt"]


# ==================== 硬字幕烧录（依赖掩码 / 传参 / 临时 SRT）====================
def test_plan_burn_subtitles_defaults_off():
    assert make_plan(srt=True, mux_original=True).burn_subtitles is False


@pytest.mark.parametrize("overrides", [
    # 没有 MP4 输出
    {"srt": True, "burn_subtitles": True},
    # 有 MP4 但识别关闭 → 没有字幕可烧
    {"model_code": "off", "srt": True, "mux_original": True, "burn_subtitles": True},
    # 视频输入 → 配图 MP4 已被掩码，烧录随之失效
    {"srt": True, "mux_original": True, "burn_subtitles": True, "has_video": True},
    # 降噪关闭但勾了降噪 MP4 → mux 被掩码，烧录同样失效
    {"denoise_code": "off", "srt": True, "mux_denoised": True, "burn_subtitles": True},
])
def test_burn_subtitles_masked_off(overrides):
    plan = make_plan(**overrides)
    assert plan.burn_subtitles is False

    flags = option_flags(
        overrides.get("model_code", BASE["model_code"]),
        overrides.get("denoise_code", BASE["denoise_code"]),
        overrides.get("srt", False),
        overrides.get("txt", False),
        overrides.get("mux_original", False),
        overrides.get("mux_denoised", False),
        overrides.get("vtt", False),
        overrides.get("burn_subtitles", False),
        has_video=overrides.get("has_video", False),
    )
    assert flags["burn_subtitles"] is False


def test_burn_subtitles_enabled_when_all_conditions_met():
    plan = make_plan(srt=True, mux_original=True, burn_subtitles=True)
    assert plan.burn_subtitles is True

    flags = option_flags("tiny", "off", True, False, True, False, False, True)
    assert flags["burn_subtitles"] is True


@pytest.mark.parametrize("overrides", [
    {"txt": True},
    {"vtt": True},
])
def test_burn_subtitles_accepts_any_subtitle_format(overrides):
    """烧录只用 SRT，但 TXT / VTT 也能触发（内部临时生成一份 SRT 给烧录用）。"""
    plan = make_plan(mux_original=True, burn_subtitles=True, **overrides)
    assert plan.burn_subtitles is True


def test_burn_subtitles_with_denoised_mp4_only():
    plan = make_plan(denoise_code="arnndn", srt=True, mux_denoised=True,
                     burn_subtitles=True)
    assert plan.mux_original is False and plan.mux_denoised is True
    assert plan.burn_subtitles is True


def test_burn_does_not_add_progress_step():
    """烧录是封装步骤的内部行为，不得新增进度节点。"""
    plain = build_steps(make_plan(srt=True, mux_original=True))
    burned = build_steps(make_plan(srt=True, mux_original=True, burn_subtitles=True))
    assert burned == plain
    assert [name for name, _a, _b in burned] == [
        pipeline_mod.STEP_STT, pipeline_mod.STEP_MUX_ORIGINAL]


def _stub_convert(monkeypatch, captured, font="Microsoft YaHei"):
    def fake_convert(ffmpeg, audio, image, out, mode, duration, on_progress,
                     should_stop, on_proc=None, loudnorm=False, sub_path=None,
                     font_name=""):
        captured.update(sub_path=sub_path, font_name=font_name,
                        progress=on_progress, loudnorm=loudnorm)
        Path(out).write_bytes(b"x")
        return 0, ""

    monkeypatch.setattr(pipeline_mod, "convert_one", fake_convert)
    monkeypatch.setattr(pipeline_mod, "detect_cjk_font", lambda: font)


def test_mux_one_forwards_subtitle_path(monkeypatch, tmp_path):
    captured = {}
    _stub_convert(monkeypatch, captured)
    plan = make_plan(srt=True, mux_original=True, burn_subtitles=True)
    sub = str(tmp_path / "sub.srt")

    ok = Pipeline(plan)._mux_one("/tmp/a.mp3", str(tmp_path / "o.mp4"), 3.0,
                                 0.0, 100.0, sub_path=sub)

    assert ok is True
    assert captured["sub_path"] == sub
    assert captured["font_name"] == "Microsoft YaHei"


def test_mux_one_ignores_subtitles_when_masked(monkeypatch, tmp_path):
    captured = {}
    _stub_convert(monkeypatch, captured)
    plan = make_plan(srt=True, mux_original=True, burn_subtitles=False)

    Pipeline(plan)._mux_one("/tmp/a.mp3", str(tmp_path / "o.mp4"), 3.0,
                            0.0, 100.0, sub_path=str(tmp_path / "sub.srt"))

    assert not captured["sub_path"]


def test_burn_temp_srt_is_generated_once(monkeypatch):
    """只勾 VTT 时内部临时生成一份 SRT；两个 MP4 步骤复用同一份。"""
    plan = make_plan(vtt=True, mux_original=True, mux_denoised=True,
                     denoise_code="arnndn", burn_subtitles=True)
    pipeline = Pipeline(plan)
    pipeline._segments = [{"start": 0.0, "end": 1.0, "text": "hello"}]

    first = pipeline._burn_subtitle_path()
    second = pipeline._burn_subtitle_path()

    assert first and first == second
    assert Path(first).is_file()
    assert len(pipeline._temps) == 1
    Path(first).unlink(missing_ok=True)


def test_burn_font_missing_logs_once(monkeypatch, tmp_path):
    """本机没有中文字体时只提示一次，且不阻塞烧录（交给 libass 自行回退）。"""
    captured = {}
    _stub_convert(monkeypatch, captured, font="")
    plan = make_plan(srt=True, mux_original=True, burn_subtitles=True)
    rec = Recorder()
    pipeline = Pipeline(plan, log=rec.log)

    for name in ("a.mp4", "b.mp4"):
        pipeline._mux_one("/tmp/a.mp3", str(tmp_path / name), 3.0, 0.0, 100.0,
                          sub_path=str(tmp_path / "sub.srt"))

    assert captured["font_name"] == ""
    from mp3tom4.i18n import t as tr

    warnings = [text for text, _err in rec.logs if text == tr("log.burn_font_missing")]
    assert len(warnings) == 1


@pytest.mark.integration
def test_flow_9_vtt_only_with_burn_keeps_srt_off_disk(monkeypatch, ffmpeg_path,
                                                      sine_audio, black_png, tmp_path):
    """勾了烧录但只勾 VTT：产物只有 .vtt + 带硬字幕的 .mp4，SRT 不落盘。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path=black_png,
        size_mode="720p", model_code="tiny", denoise_code="off",
        lang_code="auto", srt=False, txt=False, vtt=True,
        mux_original=True, mux_denoised=False, ffmpeg_path=ffmpeg_path,
        burn_subtitles=True)
    assert plan.burn_subtitles is True

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    assert sorted(path.name for path in out_dir.iterdir()) == [
        f"{stem}.mp4", f"{stem}.vtt"]
    assert 2.5 <= probe_duration(ffmpeg_path, str(out_dir / f"{stem}.mp4")) <= 3.6


@pytest.mark.integration
def test_flow_10_srt_is_reused_for_burn(monkeypatch, ffmpeg_path, sine_audio,
                                        black_png, tmp_path):
    """勾了 SRT + 烧录：直接复用那份 SRT，不额外生成第二份。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = _out_dir(tmp_path)
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path=black_png,
        size_mode="720p", model_code="tiny", denoise_code="off",
        lang_code="auto", srt=True, txt=False, vtt=False,
        mux_original=True, mux_denoised=False, ffmpeg_path=ffmpeg_path,
        burn_subtitles=True)

    run_pipeline(plan)

    stem = Path(sine_audio).stem
    assert sorted(path.name for path in out_dir.iterdir()) == [
        f"{stem}.mp4", f"{stem}.srt"]
    assert 2.5 <= probe_duration(ffmpeg_path, str(out_dir / f"{stem}.mp4")) <= 3.6
