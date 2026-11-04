# -*- coding: utf-8 -*-
"""三组功能（A 降噪 / B 字幕 / C 配图 MP4）任意组合的语义矩阵。

覆盖 14 格行为矩阵：纯音频与视频输入 × {A, B, C, AB, AC, BC, ABC}。
每格逐项断言 ``option_flags`` / ``build_plan`` 的五个字段：
need_stt、need_denoise、only_denoise、mux_original、mux_denoised。

视频输入下配图 MP4 必须被**掩码**为 False（只提取音轨），且 ``need_denoise``
只由降噪开关决定 —— 后者是「音频 + 降噪 + 原声 MP4」曾静默丢掉降噪结果的
回归防线。
"""

import inspect
import os
from types import SimpleNamespace

import pytest

from clipscribe import pipeline as pipeline_mod
from clipscribe.pipeline import Pipeline, build_plan, option_flags

# 组合定义：A = 降噪，B = 字幕（SRT），C = 原声配图 MP4
COMBOS = {
    "A": dict(model_code="off", denoise_code="arnndn"),
    "B": dict(model_code="tiny", denoise_code="off", srt=True),
    "C": dict(model_code="off", denoise_code="off", mux_original=True),
    "AB": dict(model_code="tiny", denoise_code="arnndn", srt=True),
    "AC": dict(model_code="off", denoise_code="arnndn", mux_original=True),
    "BC": dict(model_code="tiny", denoise_code="off", srt=True, mux_original=True),
    "ABC": dict(model_code="tiny", denoise_code="arnndn", srt=True,
                mux_original=True),
}
COMBO_NAMES = list(COMBOS)

# 期望值顺序：(need_stt, need_denoise, only_denoise, mux_original, mux_denoised)
EXPECTED_AUDIO = {
    "A": (False, True, True, False, False),
    "B": (True, False, False, False, False),
    "C": (False, False, False, True, False),
    "AB": (True, True, False, False, False),
    "AC": (False, True, False, True, False),
    "BC": (True, False, False, True, False),
    "ABC": (True, True, False, True, False),
}
EXPECTED_VIDEO = {
    "A": (False, True, True, False, False),
    "B": (True, False, False, False, False),
    # 只有 C：被掩码后没有任何有效动作，UI 必须报 video_need_action
    "C": (False, False, False, False, False),
    "AB": (True, True, False, False, False),
    # AC：C 被掩码掉，剩下的降噪就是唯一动作（必须真的执行）
    "AC": (False, True, True, False, False),
    "BC": (True, False, False, False, False),
    "ABC": (True, True, False, False, False),
}

CASES = [(False, name) for name in COMBO_NAMES] + \
        [(True, name) for name in COMBO_NAMES]
CASE_IDS = [f"{'video' if video else 'audio'}-{name}" for video, name in CASES]

PLAN_BASE = dict(
    audio_files=["/tmp/a.mp3"],
    output_dir="/tmp/out",
    image_path="/tmp/cover.png",
    size_mode="720p",
    lang_code="auto",
    txt=False,
    vtt=False,
    mux_denoised=False,
)


def _expected(has_video, combo):
    return (EXPECTED_VIDEO if has_video else EXPECTED_AUDIO)[combo]


def _flags(has_video, combo):
    opts = COMBOS[combo]
    return option_flags(
        opts.get("model_code", "off"),
        opts.get("denoise_code", "off"),
        opts.get("srt", False),
        opts.get("txt", False),
        opts.get("mux_original", False),
        opts.get("mux_denoised", False),
        opts.get("vtt", False),
        has_video=has_video,
    )


def _plan(has_video, combo):
    opts = COMBOS[combo]
    return build_plan(
        model_code=opts.get("model_code", "off"),
        denoise_code=opts.get("denoise_code", "off"),
        srt=opts.get("srt", False),
        mux_original=opts.get("mux_original", False),
        has_video=has_video,
        **PLAN_BASE,
    )


def _actual(source):
    if isinstance(source, dict):
        get = source.__getitem__
    else:
        get = lambda name: getattr(source, name)  # noqa: E731
    return (
        get("need_stt"),
        get("need_denoise"),
        get("only_denoise"),
        get("mux_original"),
        get("mux_denoised"),
    )


# ==================== 14 格矩阵（纯逻辑）====================
@pytest.mark.parametrize("has_video,combo", CASES, ids=CASE_IDS)
def test_option_flags_matrix(has_video, combo):
    assert _actual(_flags(has_video, combo)) == _expected(has_video, combo)


@pytest.mark.parametrize("has_video,combo", CASES, ids=CASE_IDS)
def test_build_plan_matrix(has_video, combo):
    assert _actual(_plan(has_video, combo)) == _expected(has_video, combo)


@pytest.mark.parametrize("has_video,combo", CASES, ids=CASE_IDS)
def test_flags_and_plan_agree(has_video, combo):
    """UI 摘要（flags）与实际执行计划（JobPlan）必须完全一致。"""
    assert _actual(_flags(has_video, combo)) == _actual(_plan(has_video, combo))


def test_has_video_is_last_keyword_param():
    """`has_video` 放在参数末尾，保持既有位置参数调用向后兼容。"""
    signature = inspect.signature(option_flags)
    names = list(signature.parameters)
    assert names[-1] == "has_video"
    assert signature.parameters["has_video"].default is False

    plan_signature = inspect.signature(build_plan)
    assert list(plan_signature.parameters)[-1] == "has_video"
    assert plan_signature.parameters["has_video"].default is False


def test_video_masks_denoised_mp4_even_when_denoise_on():
    """视频输入 + 降噪 + 降噪 MP4 → mux_denoised 必须被掩码，不得产出 MP4。"""
    flags = option_flags("tiny", "arnndn", True, False, False, True, False,
                         has_video=True)
    assert flags["mux_denoised"] is False
    assert flags["mux_original"] is False
    assert flags["need_denoise"] is True


def test_audio_ac_runs_denoise_despite_only_original_mux():
    """音频 + A + C：降噪不得因为「不出降噪 MP4」而被静默跳过。"""
    flags = option_flags("off", "arnndn", False, False, True, False, False)
    assert flags["need_denoise"] is True
    assert flags["only_denoise"] is False
    assert flags["mux_original"] is True


def test_build_steps_keep_weights_when_denoise_always_runs():
    """降噪在更多组合下都会执行，30/40/30 的既有权重结构保持不变。"""
    plan = _plan(False, "ABC")
    steps = pipeline_mod.build_steps(plan)
    assert [name for name, _start, _end in steps] == [
        pipeline_mod.STEP_DENOISE,
        pipeline_mod.STEP_STT,
        pipeline_mod.STEP_MUX_ORIGINAL,
    ]
    for current, following in zip(steps, steps[1:]):
        assert current[2] == pytest.approx(following[1])
    assert steps[-1][2] == pytest.approx(100.0)

    # 视频输入下 ABC 没有封装步骤：降噪 30 / 识别 40 重新归一化到 0-100
    video_steps = pipeline_mod.build_steps(_plan(True, "ABC"))
    assert [name for name, _start, _end in video_steps] == [
        pipeline_mod.STEP_DENOISE, pipeline_mod.STEP_STT]
    assert video_steps[0][1] == 0.0
    assert video_steps[-1][2] == pytest.approx(100.0)


# ==================== 真实 ffmpeg 链路（降噪必须真的执行）====================
class _Recorder:
    def __init__(self):
        self.logs = []
        self.done = 0

    def log(self, text, is_error=False):
        self.logs.append((text, is_error))

    def set_progress(self, _value):
        pass

    def set_stage(self, _text):
        pass

    def on_done(self):
        self.done += 1


def _run(plan):
    recorder = _Recorder()
    Pipeline(
        plan,
        log=recorder.log,
        set_progress=recorder.set_progress,
        set_stage=recorder.set_stage,
        should_stop=lambda: False,
        on_proc=lambda _proc: None,
        on_done=recorder.on_done,
    ).run()
    assert recorder.done == 1
    return recorder


def _fake_transcribe(audio_path, model_name, language, duration,
                     on_progress=None, should_stop=None, log=None):
    """ASR 替身：不加载 Whisper 权重，但保留真实解码 / 写盘链路。"""
    if on_progress:
        on_progress(50.0)
    return (
        [{"start": 0.0, "end": 1.0, "text": "hello"}],
        SimpleNamespace(language="en", language_probability=0.99),
    )


@pytest.mark.integration
def test_flow_audio_ac_really_denoises(ffmpeg_path, sine_audio, black_png,
                                       denoise_model, tmp_path):
    """音频 + A + C：既产出降噪 WAV（证明降噪真的跑了）又产出原声 MP4。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    plan = build_plan(
        audio_files=[sine_audio], output_dir=str(out_dir), image_path=black_png,
        size_mode="720p", model_code="off", denoise_code="arnndn",
        lang_code="auto", srt=False, txt=False,
        mux_original=True, mux_denoised=False, ffmpeg_path=ffmpeg_path,
    )
    assert plan.need_denoise is True

    _run(plan)

    stem = os.path.splitext(os.path.basename(sine_audio))[0]
    names = {path.name for path in out_dir.iterdir()}
    assert names == {f"{stem}_denoised.wav", f"{stem}.mp4"}


@pytest.mark.integration
def test_flow_video_a_only_denoises(ffmpeg_path, sine_video, denoise_model, tmp_path):
    """视频输入 + A：只产出降噪 WAV，不产出任何 MP4。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    plan = build_plan(
        audio_files=[sine_video], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="off", denoise_code="arnndn",
        lang_code="auto", srt=False, txt=False,
        mux_original=False, mux_denoised=False, ffmpeg_path=ffmpeg_path,
        has_video=True,
    )
    assert plan.only_denoise is True

    _run(plan)

    stem = os.path.splitext(os.path.basename(sine_video))[0]
    names = {path.name for path in out_dir.iterdir()}
    assert names == {f"{stem}_denoised.wav"}


# ==================== 烧录维度（在 14 格矩阵上增加 D = 硬字幕）====================
BURN_COMBOS = {
    # B + C + D：有字幕、有 MP4 → 烧录生效
    "BCD": dict(model_code="tiny", denoise_code="off", srt=True,
                mux_original=True, burn_subtitles=True),
    # B + D：只有字幕没有 MP4 → 烧录被掩码
    "BD": dict(model_code="tiny", denoise_code="off", srt=True,
               burn_subtitles=True),
}
BURN_EXPECTED_AUDIO = {"BCD": True, "BD": False}
BURN_EXPECTED_VIDEO = {"BCD": False, "BD": False}
BURN_CASES = [(has_video, name) for has_video in (False, True)
              for name in BURN_COMBOS]
BURN_IDS = [f"{'video' if has_video else 'audio'}-{name}"
            for has_video, name in BURN_CASES]


def _burn_flags(has_video, combo):
    opts = BURN_COMBOS[combo]
    return option_flags(
        opts["model_code"], opts["denoise_code"], opts["srt"], False,
        opts.get("mux_original", False), False, False, opts["burn_subtitles"],
        has_video=has_video,
    )


def _burn_plan(has_video, combo):
    opts = BURN_COMBOS[combo]
    return build_plan(
        model_code=opts["model_code"], denoise_code=opts["denoise_code"],
        srt=opts["srt"], mux_original=opts.get("mux_original", False),
        burn_subtitles=opts["burn_subtitles"], has_video=has_video,
        **PLAN_BASE,
    )


@pytest.mark.parametrize("has_video,combo", BURN_CASES, ids=BURN_IDS)
def test_burn_matrix(has_video, combo):
    expected = (BURN_EXPECTED_VIDEO if has_video else BURN_EXPECTED_AUDIO)[combo]
    assert _burn_flags(has_video, combo)["burn_subtitles"] is expected
    assert _burn_plan(has_video, combo).burn_subtitles is expected


@pytest.mark.parametrize("has_video,combo", CASES, ids=CASE_IDS)
def test_burn_is_off_by_default_in_existing_grid(has_video, combo):
    """新增维度不得改变原 14 格的任何结果：默认 burn=False。"""
    assert _plan(has_video, combo).burn_subtitles is False


def test_burn_param_sits_before_has_video():
    """`burn_subtitles` 插在 `has_video` 之前，保持 has_video 仍是最后一个参数。"""
    for func in (option_flags, build_plan):
        names = list(inspect.signature(func).parameters)
        assert names.index("burn_subtitles") < names.index("has_video")


def test_burn_allowed_helper_is_shared_source_of_truth():
    """掩码单点定义：`burn_allowed()` 与 `option_flags()` 结果一致。"""
    from clipscribe.pipeline import burn_allowed

    assert burn_allowed(True, True, True, False, False) is True
    assert burn_allowed(True, True, False, True, False) is True
    assert burn_allowed(True, True, False, False, False) is False
    assert burn_allowed(True, False, True, False, False) is False
    assert burn_allowed(True, True, True, False, True) is False
    assert burn_allowed(False, True, True, False, False) is False


@pytest.mark.integration
def test_flow_video_ab_denoise_and_subtitle(monkeypatch, ffmpeg_path, sine_video,
                                            denoise_model, tmp_path):
    """视频输入 + A + B：降噪 WAV + 字幕都在，且绝不产出 MP4。"""
    monkeypatch.setattr(pipeline_mod, "transcribe_audio", _fake_transcribe)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    plan = build_plan(
        audio_files=[sine_video], output_dir=str(out_dir), image_path="",
        size_mode="720p", model_code="tiny", denoise_code="arnndn",
        lang_code="auto", srt=True, txt=False,
        mux_original=True, mux_denoised=True, ffmpeg_path=ffmpeg_path,
        has_video=True,
    )
    assert plan.need_denoise is True
    assert plan.mux_original is False and plan.mux_denoised is False

    _run(plan)

    stem = os.path.splitext(os.path.basename(sine_video))[0]
    names = {path.name for path in out_dir.iterdir()}
    assert names == {f"{stem}_denoised.wav", f"{stem}.srt"}
    assert not any(name.endswith(".mp4") for name in names)
