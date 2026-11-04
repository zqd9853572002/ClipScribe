# -*- coding: utf-8 -*-
"""底层基础设施：常量、配置持久化、路径与轻量工具。

本模块是依赖图的最底层：只依赖标准库与 `i18n` 词条层，**不导入 ffmpeg /
denoise / pipeline / ui**。`i18n` 读取配置时采用函数内延迟导入，因此这里的
顶层 `from .i18n import t` 不会形成循环导入。

`download_file` / `remove_file_quiet` 放在此处而不是单独的 util 模块，理由：
它们只依赖标准库与本模块的 `APP_NAME` / `APP_VERSION` 常量，且 `config` 已经
是「路径与模型目录」的唯一归属（`models_root()` 就在本模块）。再拆一个 util
模块只会多一层同级依赖，不会减少耦合。
"""

import importlib.util
import json
import logging
import os
import shutil
import urllib.request
from pathlib import Path

from .i18n import t, text_for

APP_NAME = "ClipScribe"
# 5.x 及更早版本使用的目录名：**仅**用于一次性迁移旧配置与模型缓存，
# 不会出现在任何面向用户的文案里（文案走 i18n 词条）。
LEGACY_APP_NAME = "Mp3ToMp4"
APP_VERSION = "6.0.0"

# 项目根目录（原单文件脚本所在目录）：用于探测随程序放置的 ffmpeg.exe。
# 原代码用 `Path(__file__).resolve().parent`，模块化后本文件位于 <根>/clipscribe/，
# 因此取上一级，保证探测行为与拆分前完全一致。
PROJECT_ROOT = Path(__file__).resolve().parent.parent

AUDIO_EXTS = (
    ".mp3", ".m4a", ".m4b", ".aac", ".wav", ".flac", ".ogg", ".oga",
    ".opus", ".wma", ".aiff", ".aif", ".ape", ".wv", ".amr", ".ac3", ".dts",
)
# 视频容器：以 mp4 / webm 为主，其余为常见容器的顺带兼容。
# 视频只作为**输入**（取第一条音轨做识别 / 降噪），本项目不会重新封装视频画面。
VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov", ".m4v")
# 用户可选的输入文件白名单（音频 + 视频）。判断「音频专用」语义时仍用 AUDIO_EXTS。
INPUT_EXTS = AUDIO_EXTS + VIDEO_EXTS
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def is_video_file(path) -> bool:
    """按后缀（小写）判断是否为视频输入；未知 / 无后缀一律视为非视频。"""
    return Path(path).suffix.lower() in VIDEO_EXTS

# 注意：文件对话框的过滤器文案依赖当前界面语言，已移到 UI 层
# （`ui.main_window.audio_filetypes()` / `image_filetypes()`），
# 本模块只保留与语言无关的扩展名常量。

# ---------- 选项表：内部值 ↔ 文案词条 key ----------
# 所有下拉框的「值」与「文案」在此分离：
#   * 配置文件、任务计划一律使用内部值（二元组左侧），跨版本稳定；
#   * 二元组右侧是 `clipscribe/locale/*.json` 的词条 key，由 `option_label()`
#     在渲染时翻译，因此切换语言后重新渲染下拉框即可，不触碰内部值。
SIZE_OPTIONS = [
    ("1080p", "opt.size.1080p"),
    ("720p", "opt.size.720p"),
    ("orig", "opt.size.orig"),
]
STT_MODEL_OPTIONS = [
    ("off", "opt.model.off"),
    ("large-v3-turbo", "opt.model.large-v3-turbo"),
    ("medium", "opt.model.medium"),
    ("small", "opt.model.small"),
    ("base", "opt.model.base"),
    ("tiny", "opt.model.tiny"),
]
STT_LANG_OPTIONS = [
    ("auto", "opt.lang.auto"),
    ("zh", "opt.lang.zh"),
    ("en", "opt.lang.en"),
]
DENOISE_OPTIONS = [
    ("off", "opt.denoise.off"),
    ("arnndn", "opt.denoise.arnndn"),
    ("gtcrn", "opt.denoise.gtcrn"),
]

SIZE_TARGETS = {"1080p": (1920, 1080), "720p": (1280, 720)}
DEFAULT_MODE = "1080p"

# ---------- 语音识别 / 降噪 ----------
STT_OFF = "off"
DEFAULT_STT_MODEL = "large-v3-turbo"
DEFAULT_STT_LANG = "auto"
DEFAULT_DENOISE = "arnndn"

# ---------- 识别质量控制 ----------
# Whisper 的 prompt 受 token 上限约束，过长既无收益也会拖慢编码，故在 UI 与调用层
# 同时截断（UI 负责提示，这里兜住程序化调用）。
ASR_PROMPT_MAX_CHARS = 800

# ---------- 硬字幕烧录 ----------
# 新功能默认关闭：老用户升级后行为不变，且部分 ffmpeg 构建没有 libass。
DEFAULT_BURN_SUBTITLES = False

# VAD 模式 → faster-whisper `vad_parameters` 的映射。
# 注意：faster-whisper 1.2.1 的 VadOptions 字段名是 `threshold`（不是
# `vad_threshold`），传错键会直接抛 TypeError，因此这里以源码为准。
DEFAULT_VAD_MODE = "standard"
VAD_MODES = ("standard", "long")
VAD_PARAMETERS = {
    # standard 必须与 5.1.1 的实际行为逐字一致
    "standard": {"min_silence_duration_ms": 400, "speech_pad_ms": 200},
    # long：更长静音容忍 + 更大补边 + 更敏感的语音判定，减少长句被切碎
    "long": {"min_silence_duration_ms": 700, "speech_pad_ms": 300, "threshold": 0.4},
}

# 幻听后处理：仅对「时长 ≥ 阈值 且 文本命中模式」的片段生效，避免误删正常短句。
# 模式表必须放词条文件：`clipscribe/` 下的 Python 源码禁止出现中文字面量（有测试守卫）。
HALLUCINATION_MIN_DURATION_S = 3.0
HALLUCINATION_PATTERN_KEY = "asr.hallucination_patterns"

# ---------- FFmpeg 滤镜常量 ----------
# RNNoise 不可用时的兜底：频谱降噪，纯 FFmpeg 内置滤镜，零依赖。
AFFTDN_FALLBACK_FILTER = "afftdn=nf=-25:tn=1"
# 成片响度标准化（单遍）。不得用于 ASR 预处理链，否则会干扰识别。
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"
# arnndn 的干湿比；仅在模型可用时生效（1.0 = 纯降噪输出）。
DEFAULT_ARNNDN_MIX = 0.8


def option_values(options):
    """选项表的全部内部值（按显示顺序）。"""
    return [value for value, _label in options]


def _render_label(label_or_key):
    """词条 key → 当前语言文案；非 `opt.` 前缀视为已翻译好的字面量。"""
    return t(label_or_key) if label_or_key.startswith("opt.") else label_or_key


def _label_variants(label_or_key):
    """同一选项在各语言下的全部显示文案（用于旧配置反查）。"""
    if not label_or_key.startswith("opt."):
        return {label_or_key}
    variants = {label_or_key, t(label_or_key)}
    for code in ("zh_CN", "zh_TW", "en"):
        # 旧版配置里一定存的是 zh_CN 文案，必须始终可识别
        text = text_for(code, label_or_key)
        if text:
            variants.add(text)
    return variants


def option_labels(options):
    """选项表的全部显示文案（按当前界面语言）。"""
    return [_render_label(label) for _value, label in options]


def option_label(options, value, default_value=None):
    """内部值 → 当前语言的显示文案。

    同时容忍直接传入某一语言的显示文案（旧配置迁移场景）。无法识别时使用
    `default_value` 对应的文案，缺省取该组第一项。
    """
    for val, label in options:
        if value == val:
            return _render_label(label)
    for val, label in options:
        if value in _label_variants(label):
            return _render_label(label)
    fallback = default_value if default_value is not None else options[0][0]
    for val, label in options:
        if val == fallback:
            return _render_label(label)
    return _render_label(options[0][1])


def vad_parameters(mode) -> dict:
    """VAD 模式 → 传给 faster-whisper 的参数副本；未知模式回退 standard。"""
    return dict(VAD_PARAMETERS.get(mode) or VAD_PARAMETERS[DEFAULT_VAD_MODE])


def clamp_arnndn_mix(value, default: float = DEFAULT_ARNNDN_MIX) -> float:
    """把配置里的 mix 夹到 0.0–1.0；无法解析时用默认值。"""
    try:
        mix = float(value)
    except (TypeError, ValueError):
        mix = float(default)
    return max(0.0, min(1.0, mix))


def hallucination_patterns():
    """已知幻听模式（当前语言词条，已小写化）。"""
    raw = t(HALLUCINATION_PATTERN_KEY)
    return [item.strip().lower() for item in raw.split("|") if item.strip()]


def resolve_option(options, raw, default):
    """把配置/界面取到的值解析成内部值，返回 ``(内部值, 是否被识别)``。

    接受内部值，也接受**当前语言**或**旧版中文**显示文案；无法识别时回退到
    ``default``（明确指定的默认值，而不是该组第一项）。``raw`` 为空视为
    「未配置」，返回默认值且不视为异常。
    """
    if raw is None or raw == "":
        return default, True
    for value, label in options:
        if raw == value or raw == label:
            return value, True
    for value, label in options:
        if raw in _label_variants(label):
            return value, True
    return default, False

RNNOISE_URL = "https://raw.githubusercontent.com/richardpl/arnndn-models/master/bd.rnnn"
GTCRN_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speech-enhancement-models/gtcrn_simple.onnx"
)


# ==================== 旧版配置目录迁移 ====================
# 迁移结果标识：UI 层据此选择词条，翻译不落在本模块（禁止硬编码中文）
MIGRATION_MIGRATED = "migrated"
MIGRATION_SKIPPED = "skipped"
MIGRATION_ABSENT = "absent"
MIGRATION_FAILED = "failed"

# 实际生效的目录名。迁移失败时降级为旧目录名，否则 `config_file()` /
# `models_root()` 会指向一个空的新目录 —— 用户的配置丢失，1.55 GB 的
# Whisper 权重还会被重新下载。
_active_app_dir = APP_NAME
# 最近一次迁移结果：(状态, 异常简述)，异常简述由 UI 层塞进词条占位符
_last_migration = (MIGRATION_ABSENT, "")


def _base_dir(root=None) -> Path:
    """配置根目录：显式注入优先，其次 `%APPDATA%`，最后用户主目录。

    注入 `root` 是为了让测试指向临时目录；模块内不直接硬编码读 `%APPDATA%`，
    否则迁移逻辑无法在临时目录里被验证。
    """
    if root is not None:
        return Path(root)
    return Path(os.environ.get("APPDATA") or str(Path.home()))


def config_root(root=None) -> Path:
    """当前生效的配置根目录（`<base>/<目录名>`）。"""
    return _base_dir(root) / _active_app_dir


def legacy_config_root(root=None) -> Path:
    """旧版（5.x 及更早）配置根目录。"""
    return _base_dir(root) / LEGACY_APP_NAME


def active_app_dir_name() -> str:
    """当前生效的目录名（迁移失败时等于 `LEGACY_APP_NAME`）。"""
    return _active_app_dir


def last_migration():
    """最近一次 `migrate_legacy_config_dir()` 的 ``(状态, 异常简述)``。"""
    return _last_migration


def migrate_legacy_config_dir(root=None) -> str:
    """把 `%APPDATA%\\Mp3ToMp4` 一次性迁移为 `%APPDATA%\\ClipScribe`。

    返回 `MIGRATION_*` 状态字符串，且**绝不抛异常**：

    * 新目录已存在 → 什么都不做（幂等），返回 ``MIGRATION_SKIPPED``；
    * 两个目录都不存在 → 什么都不做，返回 ``MIGRATION_ABSENT``；
    * 旧目录存在 → 先 `os.replace()` 整体重命名（同盘瞬时完成、不复制），
      失败再退回 `shutil.move()`；
    * 两步都失败 → 放弃迁移并继续使用旧目录（``MIGRATION_FAILED``），
      应用仍能正常启动，模型权重不会被重新下载。

    失败时绝不删除旧目录；迁移成功后旧目录已经不存在（被重命名）。
    """
    global _active_app_dir, _last_migration

    new_dir = _base_dir(root) / APP_NAME
    old_dir = _base_dir(root) / LEGACY_APP_NAME

    if new_dir.exists():
        # 幂等：新目录已存在则既不覆盖也不合并，更不碰旧目录
        _active_app_dir = APP_NAME
        _last_migration = (MIGRATION_SKIPPED, "")
        return MIGRATION_SKIPPED

    if not old_dir.exists():
        _active_app_dir = APP_NAME
        _last_migration = (MIGRATION_ABSENT, "")
        return MIGRATION_ABSENT

    try:
        os.replace(str(old_dir), str(new_dir))
    except Exception as exc_replace:
        try:
            shutil.move(str(old_dir), str(new_dir))
        except Exception as exc_move:
            # shutil.move 是「复制 + 删除」，中途失败可能留下半成品新目录。
            # 此时旧目录仍完整，清掉半成品，避免下次启动把半成品误判成
            # 「已迁移」而让用户丢掉模型。
            if old_dir.exists():
                shutil.rmtree(str(new_dir), ignore_errors=True)
            _active_app_dir = LEGACY_APP_NAME
            detail = f"{exc_replace} / {exc_move}"
            _last_migration = (MIGRATION_FAILED, detail)
            logging.warning("ClipScribe: config dir migration failed: %s", detail)
            return MIGRATION_FAILED

    _active_app_dir = APP_NAME
    _last_migration = (MIGRATION_MIGRATED, "")
    logging.info("ClipScribe: config dir migrated %s -> %s", old_dir, new_dir)
    return MIGRATION_MIGRATED


# ==================== 配置持久化 ====================
def config_file() -> Path:
    return config_root() / "config.json"


def load_config() -> dict:
    try:
        with open(config_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        path = config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def legacy_subtitle_flags(cfg: dict):
    """把旧配置（v4.0 只有 `stt_enabled`）折算成 (srt, txt) 两个开关。

    旧键语义为「同时生成两种格式」；显式写过的 `srt_enabled` / `txt_enabled`
    优先于旧键。
    """
    legacy_stt = cfg.get("stt_enabled")
    legacy_flag = bool(legacy_stt) if legacy_stt is not None else False
    return (
        bool(cfg.get("srt_enabled", legacy_flag)),
        bool(cfg.get("txt_enabled", legacy_flag)),
    )


# ==================== 路径 / 依赖 / 下载 ====================
def models_root() -> Path:
    """模型缓存根目录；迁移失败时仍在旧目录，避免重复下载权重。"""
    return config_root() / "models"


def module_available(name: str) -> bool:
    """只检查模块是否存在，不真正导入（避免启动变慢）。"""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def download_file(url: str, dest: Path, log=None, label: str = "") -> bool:
    """带 .part 临时文件的小文件下载，失败不抛异常。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        if log:
            log(t("log.download_start", label=label, name=dest.name))
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        done = 0
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
        tmp.replace(dest)
        if log:
            log(t("log.download_done", name=dest.name, size=done / 1048576))
        return True
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        if log:
            log(t("log.download_failed", exc=exc), True)
        return False


def remove_file_quiet(path: str) -> None:
    """删除文件，失败也不抛异常。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
