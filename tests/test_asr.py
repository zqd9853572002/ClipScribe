# -*- coding: utf-8 -*-
"""asr 模块：initial_prompt 透传、VAD 参数映射、幻听抑制参数与后处理过滤。

不加载任何 Whisper 权重：模型、WAV 读取全部用替身，只验证「传给模型的参数」
与「返回段落的过滤语义」。
"""

from types import SimpleNamespace

import pytest

from clipscribe import asr
from clipscribe.config import (
    ASR_PROMPT_MAX_CHARS,
    HALLUCINATION_MIN_DURATION_S,
    hallucination_patterns,
    vad_parameters,
)


class _FakeSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


class _FakeModel:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, samples, **kwargs):
        self.kwargs = kwargs
        return iter([_FakeSegment(0.0, 1.0, "hello")]), SimpleNamespace(
            language="en", language_probability=0.9)


@pytest.fixture()
def fake_model(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(asr, "get_whisper_model", lambda name, log=None: model)
    monkeypatch.setattr(asr, "read_wav_float32", lambda path: ("samples", 16000))
    return model


def _run(model, **kwargs):
    return asr.transcribe_audio(
        "input.wav", "tiny", None, 1.0, None, lambda: False, **kwargs)


# ==================== initial_prompt ====================
def test_initial_prompt_is_forwarded(fake_model):
    _run(fake_model, initial_prompt="Acme Corp, 张伟")
    assert fake_model.kwargs["initial_prompt"] == "Acme Corp, 张伟"


def test_initial_prompt_empty_or_none_is_not_forwarded(fake_model):
    _run(fake_model, initial_prompt="")
    assert "initial_prompt" not in fake_model.kwargs

    _run(fake_model, initial_prompt=None)
    assert "initial_prompt" not in fake_model.kwargs

    _run(fake_model, initial_prompt="   ")
    assert "initial_prompt" not in fake_model.kwargs


def test_initial_prompt_is_truncated(fake_model):
    _run(fake_model, initial_prompt="x" * (ASR_PROMPT_MAX_CHARS + 50))
    assert len(fake_model.kwargs["initial_prompt"]) == ASR_PROMPT_MAX_CHARS


# ==================== VAD 参数映射 ====================
def test_vad_standard_matches_current_behavior(fake_model):
    """standard 必须与 5.1.1 的硬编码值逐字一致。"""
    _run(fake_model, vad_mode="standard")
    assert fake_model.kwargs["vad_parameters"] == {
        "min_silence_duration_ms": 400, "speech_pad_ms": 200}


def test_vad_long_parameters(fake_model):
    """long 模式：700ms / 300ms / 0.4（faster-whisper 的键名是 threshold）。"""
    _run(fake_model, vad_mode="long")
    params = fake_model.kwargs["vad_parameters"]
    assert params["min_silence_duration_ms"] == 700
    assert params["speech_pad_ms"] == 300
    assert params["threshold"] == 0.4


def test_vad_unknown_mode_falls_back_to_standard():
    assert vad_parameters("不存在") == vad_parameters("standard")


# ==================== 幻听抑制参数 ====================
def test_hallucination_mitigation_options(fake_model):
    """word_timestamps 关闭，因此走阈值收紧 + 后处理过滤的组合。"""
    _run(fake_model)
    kwargs = fake_model.kwargs
    assert kwargs["no_speech_threshold"] == 0.5
    assert kwargs["log_prob_threshold"] == -1.0
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["word_timestamps"] is False
    # 依赖 word_timestamps 的参数不得传入（传了也不会生效）
    assert "hallucination_silence_threshold" not in kwargs


# ==================== 幻听后处理 ====================
PATTERNS = ["谢谢观看", "字幕由", "thanks for watching"]


@pytest.mark.parametrize("start,end,text,dropped", [
    # 超长静音段 + 命中模式 → 丢弃
    (10.0, 14.0, "谢谢观看", True),
    (0.0, 5.0, "字幕由某某团队提供", True),
    (2.0, 8.0, "Thanks for watching", True),
    # 正常短句命中模式 → 保留（避免误删真实内容）
    (0.0, 1.5, "谢谢观看", False),
    (3.0, 3.5, "字幕由某某团队提供", False),
    # 超长但内容正常 → 保留
    (10.0, 14.0, "这是正常讲解内容", False),
    # 缺少时长字段 → 保留（不因数据异常丢字幕）
    (None, None, "谢谢观看", False),
])
def test_filter_hallucination_segments(start, end, text, dropped):
    segment = {"start": start, "end": end, "text": text}
    kept = asr.filter_hallucination_segments([segment], patterns=PATTERNS)
    assert (kept == []) is dropped


def test_filter_uses_configured_min_duration():
    segment = {"start": 0.0, "end": HALLUCINATION_MIN_DURATION_S, "text": "谢谢观看"}
    assert asr.filter_hallucination_segments([segment], patterns=PATTERNS) == []


def test_filter_keeps_normal_segments_untouched():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "第一句"},
        {"start": 1.0, "end": 2.0, "text": "第二句"},
    ]
    assert asr.filter_hallucination_segments(segments, patterns=PATTERNS) == segments


def test_default_patterns_cover_chinese_and_english():
    """默认模式表来自词条，必须能同时命中中英文幻听。"""
    patterns = hallucination_patterns()
    assert any("谢谢观看" in item for item in patterns)
    assert any("thanks for watching" in item for item in patterns)
