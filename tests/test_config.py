# -*- coding: utf-8 -*-
"""config 模块：常量完整性、配置读写 round-trip、旧配置键兼容。"""

import json
from pathlib import Path

import pytest

from clipscribe import config
from clipscribe.i18n import t

PYPROJECT = Path(config.__file__).resolve().parent.parent / "pyproject.toml"


def test_constants_complete():
    # 6.0.0：项目改名为 ClipScribe，配置目录名同步改名
    assert config.APP_NAME == "ClipScribe"
    # 旧目录名只作为迁移来源保留，不得再被路径函数使用
    assert config.LEGACY_APP_NAME == "Mp3ToMp4"
    assert config.APP_VERSION
    # 应用标题已外置为词条（config 不再持有中文字面量）
    assert t("app.title")

    assert config.AUDIO_EXTS
    assert all(ext.startswith(".") for ext in config.AUDIO_EXTS)
    assert ".mp3" in config.AUDIO_EXTS
    assert ".wav" in config.AUDIO_EXTS
    assert config.IMAGE_EXTS
    assert all(ext.startswith(".") for ext in config.IMAGE_EXTS)


def test_video_exts_and_input_exts():
    """视频容器白名单 + 合并后的输入白名单保持一致。"""
    assert config.VIDEO_EXTS == (".mp4", ".webm", ".mkv", ".mov", ".m4v")
    assert all(ext.startswith(".") for ext in config.VIDEO_EXTS)
    # 合并常量必须是「音频 + 视频」，且不能把音频从白名单里挤掉
    assert config.INPUT_EXTS == config.AUDIO_EXTS + config.VIDEO_EXTS
    assert set(config.AUDIO_EXTS).isdisjoint(config.VIDEO_EXTS)
    assert ".mp3" in config.INPUT_EXTS and ".mp4" in config.INPUT_EXTS


def test_is_video_file_detection():
    """后缀判定：大小写不敏感、未知 / 无后缀 / 空值一律为 False。"""
    assert config.is_video_file("clip.mp4") is True
    assert config.is_video_file("CLIP.MP4") is True
    assert config.is_video_file("C:/media/demo.WebM") is True
    assert config.is_video_file("a.mkv") is True
    assert config.is_video_file("a.mov") is True
    assert config.is_video_file("a.m4v") is True

    assert config.is_video_file("a.mp3") is False
    assert config.is_video_file("a.wav") is False
    assert config.is_video_file("a.srt") is False
    assert config.is_video_file("noextension") is False
    assert config.is_video_file("") is False

    assert config.DEFAULT_MODE == "1080p"
    assert config.DEFAULT_MODE in config.SIZE_TARGETS
    assert set(config.option_values(config.SIZE_OPTIONS)) == {"1080p", "720p", "orig"}
    assert config.SIZE_TARGETS["1080p"] == (1920, 1080)
    assert config.SIZE_TARGETS["720p"] == (1280, 720)

    assert config.STT_OFF == "off"
    assert ("off", "opt.model.off") in config.STT_MODEL_OPTIONS
    assert config.DEFAULT_STT_MODEL in config.option_values(config.STT_MODEL_OPTIONS)
    assert config.DEFAULT_STT_LANG in config.option_values(config.STT_LANG_OPTIONS)
    assert config.DEFAULT_DENOISE == "arnndn"
    assert ("off", "opt.denoise.off") in config.DENOISE_OPTIONS
    assert config.DEFAULT_DENOISE in config.option_values(config.DENOISE_OPTIONS)


def test_version_matches_pyproject():
    """版本号单一来源：pyproject 的 version 必须与 config.APP_VERSION 一致。"""
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+ 才有标准库 tomllib
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["project"]["version"] == config.APP_VERSION
    # 6.0.0：包名 / 配置目录改名属破坏性变更（major 升级）
    assert config.APP_VERSION == "6.0.0"


def test_option_tables_are_value_label_pairs():
    """四组选项均为 (内部值, 词条 key)：内部值唯一、key 唯一、顺序稳定。"""
    for options in (config.SIZE_OPTIONS, config.STT_MODEL_OPTIONS,
                    config.STT_LANG_OPTIONS, config.DENOISE_OPTIONS):
        assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in options)
        values = config.option_values(options)
        labels = config.option_labels(options)
        assert len(values) == len(set(values))
        assert len(labels) == len(set(labels))
        assert all(value and label for value, label in options)
        # 文案列一律是 `opt.` 前缀的词条 key
        assert all(label.startswith("opt.") for _value, label in options)

    # 选项集合与拆分前完全一致（不新增、不删除）
    assert config.option_labels(config.SIZE_OPTIONS) == [
        t("opt.size.1080p"), t("opt.size.720p"), t("opt.size.orig")]
    assert config.option_values(config.STT_MODEL_OPTIONS) == [
        "off", "large-v3-turbo", "medium", "small", "base", "tiny"]
    assert config.option_values(config.STT_LANG_OPTIONS) == ["auto", "zh", "en"]
    assert config.option_values(config.DENOISE_OPTIONS) == ["off", "arnndn", "gtcrn"]


def test_option_label_maps_internal_value():
    assert config.option_label(config.SIZE_OPTIONS, "720p") == "720p (1280x720)"
    assert config.option_label(
        config.STT_MODEL_OPTIONS, "tiny") == t("opt.model.tiny")
    # 也容忍直接传入旧显示文案（旧配置迁移）
    assert config.option_label(config.DENOISE_OPTIONS, "关闭") == "关闭"
    # 无法识别时用默认值对应的文案
    assert config.option_label(
        config.STT_MODEL_OPTIONS, "??", config.DEFAULT_STT_MODEL
    ) == t("opt.model.large-v3-turbo")


def test_resolve_option_accepts_internal_value_and_legacy_label():
    assert config.resolve_option(config.SIZE_OPTIONS, "720p", "1080p") == ("720p", True)
    assert config.resolve_option(
        config.SIZE_OPTIONS, "720p (1280x720)", "1080p") == ("720p", True)
    assert config.resolve_option(
        config.DENOISE_OPTIONS, "轻度 · RNNoise（推荐）", "arnndn") == ("arnndn", True)
    assert config.resolve_option(
        config.STT_LANG_OPTIONS, "中文", "auto") == ("zh", True)


def test_resolve_option_unknown_falls_back_to_explicit_default():
    value, recognized = config.resolve_option(
        config.STT_MODEL_OPTIONS, "不存在的模型", config.DEFAULT_STT_MODEL)
    assert (value, recognized) == (config.DEFAULT_STT_MODEL, False)
    # 关键：回退目标是默认模型而不是第一项（"off" 会静默关闭识别）
    assert value != config.STT_OFF

    assert config.resolve_option(config.SIZE_OPTIONS, "", "1080p") == ("1080p", True)
    assert config.resolve_option(config.SIZE_OPTIONS, None, "720p") == ("720p", True)
    assert config.resolve_option(config.SIZE_OPTIONS, "??", "720p") == ("720p", False)


def test_config_paths_use_new_appdata_layout(monkeypatch, tmp_path):
    """配置与模型路径落在 %APPDATA%\\ClipScribe 下，且不再指向旧目录名。"""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.config_file() == tmp_path / "ClipScribe" / "config.json"
    assert config.models_root() == tmp_path / "ClipScribe" / "models"
    # 旧目录名只能出现在迁移来源里
    assert config.legacy_config_root() == tmp_path / "Mp3ToMp4"
    assert "Mp3ToMp4" not in str(config.config_file())
    assert "Mp3ToMp4" not in str(config.models_root())


def test_config_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.load_config() == {}

    data = {
        "size_mode": "720p",
        "stt_model": "tiny",
        "srt_enabled": True,
        "txt_enabled": False,
        "mux_original": True,
        "备注": "中文内容",
    }
    config.save_config(data)

    raw = config.config_file().read_text(encoding="utf-8")
    assert json.loads(raw) == data
    assert "中文内容" in raw, "配置必须保持 ensure_ascii=False 的中文可读性"
    assert config.load_config() == data


def test_load_config_tolerates_broken_json(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = config.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text("{not json", encoding="utf-8")
    assert config.load_config() == {}

    path.write_text("[]", encoding="utf-8")
    assert config.load_config() == {}


def test_legacy_stt_enabled_maps_to_srt_and_txt():
    assert config.legacy_subtitle_flags({}) == (False, False)
    assert config.legacy_subtitle_flags({"stt_enabled": True}) == (True, True)
    assert config.legacy_subtitle_flags({"stt_enabled": False}) == (False, False)
    # 新键优先于旧键
    assert config.legacy_subtitle_flags(
        {"stt_enabled": True, "srt_enabled": False}) == (False, True)
    assert config.legacy_subtitle_flags(
        {"stt_enabled": False, "txt_enabled": True}) == (False, True)
    assert config.legacy_subtitle_flags(
        {"stt_enabled": True, "srt_enabled": True, "txt_enabled": False}) == (True, False)


def test_module_available():
    assert config.module_available("json") is True
    assert config.module_available("definitely_not_a_module_xyz") is False
