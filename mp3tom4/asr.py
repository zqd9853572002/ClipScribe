# -*- coding: utf-8 -*-
"""Whisper 模型管理与语音识别。

允许依赖 `config`、`denoise`（转写链路需要读取 16k 单声道 WAV）。
"""

import os

from .config import (
    ASR_PROMPT_MAX_CHARS,
    DEFAULT_VAD_MODE,
    HALLUCINATION_MIN_DURATION_S,
    hallucination_patterns,
    models_root,
    vad_parameters,
)
from .denoise import read_wav_float32
from .i18n import t

_WHISPER_CACHE = {}


def whisper_model_ready(model_name: str) -> bool:
    """判断 HuggingFace 缓存里是否已有该模型的权重。"""
    root = models_root() / "whisper"
    if not root.is_dir():
        return False
    for repo in root.glob("models--*"):
        if repo.name.endswith(model_name) and any(repo.rglob("model.bin")):
            return True
    return False


def get_whisper_model(model_name: str, log=None):
    """加载并缓存 Whisper 模型（同一时间只保留一个，避免内存叠加）。"""
    model = _WHISPER_CACHE.get(model_name)
    if model is not None:
        return model
    from faster_whisper import WhisperModel

    for key in list(_WHISPER_CACHE):
        if key != model_name:
            _WHISPER_CACHE.pop(key, None)

    root = str(models_root() / "whisper")
    os.makedirs(root, exist_ok=True)
    if not whisper_model_ready(model_name) and log:
        log(t("log.model_downloading"))
        log(t("log.model_mirror_hint"))
    model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=root)
    _WHISPER_CACHE[model_name] = model
    if log:
        log(t("log.model_loaded"))
    return model


def transcribe_audio(audio_path: str, model_name: str, language, duration: float,
                     on_progress, should_stop, log=None,
                     initial_prompt: str | None = None, vad_mode: str = DEFAULT_VAD_MODE):
    """转写 16k 单声道 WAV，返回 (segments, info)。segments 为 [{start, end, text}]。

    `initial_prompt` 只在非空时才传给模型，避免空串改写 Whisper 的默认解码上下文。
    `vad_mode` 映射见 `config.VAD_PARAMETERS`：standard 与 5.1.1 行为完全一致。

    幻听抑制说明：faster-whisper 1.2.1 的 `hallucination_silence_threshold`
    只在 `word_timestamps=True` 分支内生效（transcribe.py:1278-1295），本项目
    不开词级时间戳，因此改用「收紧 no_speech_threshold + log_prob_threshold
    + 关闭上文条件」组合，并在 pipeline 里做后处理过滤。
    """
    model = get_whisper_model(model_name, log)
    samples, rate = read_wav_float32(audio_path)
    if int(rate) != 16000:
        raise ValueError(t("err.sample_rate", rate=rate))

    options = {
        "language": language,
        "beam_size": 5,
        "vad_filter": True,
        "vad_parameters": vad_parameters(vad_mode),
        "condition_on_previous_text": False,
        # 更倾向把静音判为「无语音」，并丢弃低置信度片段
        "no_speech_threshold": 0.5,
        "log_prob_threshold": -1.0,
        "word_timestamps": False,
    }
    prompt = (initial_prompt or "").strip()
    if prompt:
        options["initial_prompt"] = prompt[:ASR_PROMPT_MAX_CHARS]

    # 直接传 numpy 数组，绕开 faster-whisper 内置的 PyAV 解码路径
    segments, info = model.transcribe(samples, **options)
    result = []
    for seg in segments:
        if should_stop():
            break
        text = (seg.text or "").strip()
        if text:
            result.append({"start": float(seg.start), "end": float(seg.end), "text": text})
        if duration > 0 and on_progress:
            on_progress(min(99.0, max(0.0, float(seg.end) / duration * 100.0)))
    if on_progress:
        on_progress(99.0 if result else 0.0)
    return result, info


def filter_hallucination_segments(segments, min_duration=HALLUCINATION_MIN_DURATION_S,
                                  patterns=None):
    """丢弃「超长 + 命中已知幻听模式」的片段。

    只对**长时间段**生效，正常一两秒的「谢谢观看」不会被误删；模式表来自词条
    （`config.HALLUCINATION_PATTERN_KEY`），因此能同时覆盖中英文幻听。
    """
    if patterns is None:
        patterns = hallucination_patterns()
    kept = []
    for seg in segments:
        try:
            span = float(seg["end"]) - float(seg["start"])
        except (KeyError, TypeError, ValueError):
            span = 0.0
        text = str(seg.get("text") or "").lower()
        if span >= float(min_duration) and any(p in text for p in patterns):
            continue
        kept.append(seg)
    return kept
