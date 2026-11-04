# -*- coding: utf-8 -*-
"""FFmpeg 探测、时长解析、滤镜构造、封装与流式调用。

只允许依赖 `config`。
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import LOUDNORM_FILTER, PROJECT_ROOT, SIZE_TARGETS

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# ==================== 字幕烧录（硬字幕）常量 ====================
# 烧录时复制到临时 ASCII 目录里的字幕文件名：滤镜里只出现相对路径，
# 中文 / 空格 / 盘符冒号因此完全绕开（见 `convert_one()`）。
SUB_COPY_NAME = "sub.srt"
# 中文字体优先级：微软雅黑 → Noto Sans CJK；都不存在就不传 FontName，
# 交给 libass 自行回退（可能掉字，由调用方记一条日志）。
FONT_CANDIDATES = (
    ("Microsoft YaHei", ("msyh.ttc", "msyh.ttf", "msyhbd.ttc", "msyhl.ttc")),
    ("Noto Sans CJK SC", ("notosanscjk-regular.ttc", "notosanscjksc-regular.otf",
                          "notosanssc-regular.otf", "notosanssc-regular.ttf")),
)
# 字幕样式按输出高度等比缩放：字号 3%、底边距 4%，并夹在合理区间内
BURN_SIZE_RATIO = 0.03
BURN_SIZE_RANGE = (16, 48)
BURN_MARGIN_RATIO = 0.04
BURN_MARGIN_RANGE = (10, 80)
# 「原图尺寸」无法静态得知输出高度，用 1080 作为字号基准
DEFAULT_BURN_HEIGHT = 1080
_font_cache = None


def run_quiet(args, timeout=30):
    """静默执行命令，永不抛异常。"""
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            errors="replace", creationflags=NO_WINDOW,
        )
    except Exception:
        return None


def has_filter(filters_text, name):
    """从 `ffmpeg -filters` 输出里判断某个滤镜是否可用。

    输出形如 `` .. subtitles         V->V       Render text ...``：
    第一列是能力标记（T/./S 组合），第二列是滤镜名，第三列是输入→输出类型。
    """
    if not filters_text or not name:
        return False
    pattern = rf"^\s*\S+\s+{re.escape(name)}\s+\S*->\S*"
    return re.search(pattern, filters_text, re.MULTILINE) is not None


def ffmpeg_info(path: str):
    """返回 ffmpeg 的版本与能力；无效路径返回 None。

    `libx264` / `aac` 是**必需能力**（缺了无法产出兼容 MP4，会被跳过），
    `subtitles` 只是**可选能力**（缺 libass 时仅不能烧录硬字幕，其余功能照常）。
    """
    if not path or not os.path.isfile(path):
        return None
    ver = run_quiet([path, "-hide_banner", "-version"], timeout=20)
    if not ver or ver.returncode != 0:
        return None
    text = (ver.stdout or "") + (ver.stderr or "")
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    enc = run_quiet([path, "-hide_banner", "-encoders"], timeout=20)
    enc_text = ((enc.stdout or "") + (enc.stderr or "")) if enc else ""
    filt = run_quiet([path, "-hide_banner", "-filters"], timeout=20)
    filt_text = ((filt.stdout or "") + (filt.stderr or "")) if filt else ""
    return {
        "path": path,
        "version": first,
        "libx264": "libx264" in enc_text,
        "aac": re.search(r"\baac\b", enc_text) is not None,
        # 可选能力：libass 提供的 subtitles 滤镜
        "subtitles": has_filter(filt_text, "subtitles"),
    }


def ffmpeg_candidates(saved=None):
    """按优先级生成候选 ffmpeg 路径。"""
    found = []

    def add(p):
        if p and p not in found:
            found.append(p)

    add(saved)
    here = PROJECT_ROOT
    add(str(here / "ffmpeg.exe"))
    add(str(here / "bin" / "ffmpeg.exe"))
    add(shutil.which("ffmpeg"))

    local = os.environ.get("LOCALAPPDATA", "")
    patterns = [
        os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
        os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"),
        os.path.join(local, "Microsoft", "WinGet", "Packages", "BtbN.FFmpeg*", "**", "bin", "ffmpeg.exe"),
        os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "bin", "ffmpeg.exe"),
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Files\Software\ffmpeg\bin\ffmpeg.exe",
        r"C:\Files\Software\FormatFactory\ffmpeg.exe",
        os.path.join(local, "JianyingPro", "Apps", "*", "ffmpeg.exe"),
    ]
    for pattern in patterns:
        try:
            for hit in sorted(glob.glob(pattern, recursive=True), reverse=True):
                add(hit)
        except Exception:
            pass

    try:  # 可选依赖：装了 imageio-ffmpeg 也能用
        import imageio_ffmpeg

        add(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    return found


def discover_ffmpeg(saved=None):
    """返回 (可用的 ffmpeg 信息列表, 不可用但存在的列表)。"""
    usable, rejected = [], []
    for path in ffmpeg_candidates(saved):
        info = ffmpeg_info(path)
        if not info:
            continue
        (usable if (info["libx264"] and info["aac"]) else rejected).append(info)
    return usable, rejected


def probe_duration(ffmpeg: str, audio_path: str) -> float:
    """用 ffmpeg -i 的输出解析音频时长（秒）。"""
    res = run_quiet([ffmpeg, "-hide_banner", "-i", audio_path], timeout=30)
    text = ((res.stdout or "") + (res.stderr or "")) if res else ""
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def output_height(mode: str) -> int:
    """烧录字号的基准高度：固定档位取目标高度，原图尺寸用默认基准。"""
    target = SIZE_TARGETS.get(mode)
    return target[1] if target else DEFAULT_BURN_HEIGHT


def burn_style(height, font_name=""):
    """构造 force_style 的参数串（不含外层引号），字号与边距随输出高度变化。"""
    size = max(BURN_SIZE_RANGE[0], min(BURN_SIZE_RANGE[1],
                                        round(height * BURN_SIZE_RATIO)))
    margin = max(BURN_MARGIN_RANGE[0], min(BURN_MARGIN_RANGE[1],
                                           round(height * BURN_MARGIN_RATIO)))
    parts = []
    font = (font_name or "").replace("'", "").replace(":", "").strip()
    if font:
        parts.append(f"FontName={font}")
    parts += [f"FontSize={size}", "Outline=2", "Shadow=0", f"MarginV={margin}"]
    return ",".join(parts)


def subtitle_filter(mode: str, sub_name: str, font_name="") -> str:
    """`subtitles=` 滤镜：必须排在 scale/pad 之后，字号才以输出像素计。

    单个逗号 / 冒号在 avfilter 里是参数分隔符，因此整个 force_style 用单引号
    包裹（实测 ffmpeg 9.0.2 直接把它当 argv 传入即可正确解析）。
    """
    style = burn_style(output_height(mode), font_name)
    return f"subtitles={sub_name}:force_style='{style}'"


def build_video_filter(mode: str, sub_name=None, font_name="") -> str:
    """构造缩放/补边滤镜，保证输出宽高为偶数，并统一为 yuv420p(tv)。

    JPEG 封面的输入是 full-range（yuvj420p），不显式 format 会在输出里保留
    full-range 标记，导致播放器/YouTube 上出现色彩偏移，因此这里强制转换。

    烧录硬字幕时把 `subtitles=` 追加到**链尾**（scale/pad/format 之后）：
    libass 按最终输出分辨率渲染，字号与边距才是所见即所得。
    """
    if mode == "orig":
        expr = "scale=trunc(iw/2)*2:trunc(ih/2)*2:out_range=tv,format=yuv420p"
    else:
        width, height = SIZE_TARGETS[mode]
        expr = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:out_range=tv,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
            f"format=yuv420p"
        )
    if sub_name:
        expr = f"{expr},{subtitle_filter(mode, sub_name, font_name)}"
    return expr


def font_dirs():
    """Windows 常见字体目录（系统目录 + 当前用户目录）。"""
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    dirs = [os.path.join(windir, "Fonts")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    return dirs


def detect_cjk_font(dirs=None):
    """按优先级返回本机存在的中文字体名；都不存在返回空串（默认目录结果缓存）。

    只查字体文件名，不引入任何依赖，也不需要启动额外进程。
    """
    global _font_cache
    use_cache = dirs is None
    if use_cache:
        if _font_cache is not None:
            return _font_cache
        dirs = font_dirs()
    for folder in dirs:
        try:
            names = {item.lower() for item in os.listdir(folder)}
        except Exception:
            continue
        for family, filenames in FONT_CANDIDATES:
            if any(name in names for name in filenames):
                if use_cache:
                    _font_cache = family
                return family
    return ""


def unique_path(path: str) -> str:
    """同名文件已存在时自动追加序号，避免覆盖。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{stem} ({index}){ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def filter_escape_path(path: str) -> str:
    """FFmpeg 滤镜参数里的 Windows 路径需要转义盘符冒号。"""
    return path.replace("\\", "/").replace(":", "\\:")


def build_convert_cmd(ffmpeg, audio_path, image_path, out_path, mode, loudnorm=False,
                      duration=0.0, sub_name=None, font_name=""):
    """构造成片封装命令（纯函数，便于测试响度标准化开关与字幕烧录）。

    `sub_name` 是**滤镜里引用的相对文件名**（由 `convert_one()` 在临时 ASCII
    目录里准备好），不是用户路径；`None` 表示不烧录。
    """
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "1", "-i", image_path,
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", build_video_filter(mode, sub_name=sub_name, font_name=font_name),
    ]
    # 响度标准化只作用于成片音轨；调用方若传入的已是降噪 WAV，
    # 这里自然形成「降噪链 → loudnorm」的顺序。
    if loudnorm:
        cmd += ["-af", LOUDNORM_FILTER]
        # 单遍 loudnorm 会缓冲音频，配合无限循环封面时 -shortest 无法及时
        # 结束（实测 ffmpeg 9.0.2 会产出 ~42 秒的空白），因此显式限定时长。
        if duration > 0:
            cmd += ["-t", f"{duration:.3f}"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-r", "1",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest",
        "-progress", "pipe:1", "-nostats",
        out_path,
    ]
    return cmd


def _stream(cmd, duration, should_stop, on_progress=None, on_proc=None, cwd=None):
    """执行 ffmpeg 命令并解析 -progress 输出，返回 (returncode, stderr 文本)。

    `cwd` 会原样透传给子进程：烧录字幕时用它把工作目录切到临时 ASCII 目录，
    滤镜里因此只需写相对文件名。
    """
    err_file = tempfile.TemporaryFile(mode="w+b")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=err_file, cwd=cwd,
        creationflags=NO_WINDOW, universal_newlines=True, bufsize=1,
    )
    if on_proc is not None:
        on_proc(proc)
    try:
        for line in proc.stdout:
            if should_stop():
                proc.terminate()
                break
            line = line.strip()
            if line.startswith("out_time_us=") and on_progress and duration > 0:
                value = line.split("=", 1)[1]
                if value.lstrip("-").isdigit():
                    on_progress(min(99.0, int(value) / 1_000_000.0 / duration * 100.0))
        proc.wait()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        if on_proc is not None:
            on_proc(None)

    err_file.seek(0)
    err_text = err_file.read().decode("utf-8", "replace").strip()
    err_file.close()
    return proc.returncode, err_text


def convert_one(ffmpeg, audio_path, image_path, out_path, mode, duration, on_progress, should_stop,
                on_proc=None, loudnorm=False, sub_path=None, font_name=""):
    """执行单个转换，返回 (returncode, stderr 文本)。

    on_proc 为可选回调：子进程启动时回调 Popen 句柄、结束时回调 None，
    让 GUI 的取消按钮可以直接 terminate 真正的 ffmpeg 进程。

    `sub_path` 非空时烧录硬字幕。Windows 路径（中文 / 空格 / 盘符冒号）绝不能
    直接塞进 `subtitles=` 滤镜，因此：建一个唯一临时目录 → 把字幕复制成该目录
    下的纯 ASCII 文件名 `sub.srt` → 子进程用 `cwd=<临时目录>` 启动 → 滤镜只写
    `subtitles=sub.srt:...`。封面图 / 音频 / 输出仍用绝对路径（它们不在滤镜里）。
    无论成功失败（含取消、异常）都清理该临时目录。
    """
    if not sub_path:
        cmd = build_convert_cmd(ffmpeg, audio_path, image_path, out_path, mode,
                                loudnorm=loudnorm, duration=duration)
        return _stream(cmd, duration, should_stop, on_progress, on_proc)

    audio_path = os.path.abspath(audio_path)
    image_path = os.path.abspath(image_path)
    out_path = os.path.abspath(out_path)
    workdir = tempfile.mkdtemp(prefix="clipscribe_burn_")
    try:
        try:
            shutil.copyfile(sub_path, os.path.join(workdir, SUB_COPY_NAME))
        except Exception:
            # 字幕不可读时退回普通封装：至少产出无字幕成片，不中断批量任务
            cmd = build_convert_cmd(ffmpeg, audio_path, image_path, out_path, mode,
                                    loudnorm=loudnorm, duration=duration)
            return _stream(cmd, duration, should_stop, on_progress, on_proc)
        cmd = build_convert_cmd(ffmpeg, audio_path, image_path, out_path, mode,
                                loudnorm=loudnorm, duration=duration,
                                sub_name=SUB_COPY_NAME, font_name=font_name)
        return _stream(cmd, duration, should_stop, on_progress, on_proc, cwd=workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_ffmpeg_stream(cmd, duration, should_stop, on_progress=None, on_proc=None):
    """执行 ffmpeg 命令并解析 -progress 输出，返回 (returncode, stderr 文本)。"""
    return _stream(cmd, duration, should_stop, on_progress, on_proc)
