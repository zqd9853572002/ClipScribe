# -*- coding: utf-8 -*-
"""字幕/文本产物生成：时间戳格式化、按显示宽度折行、SRT/VTT/TXT 写入。

**纯函数模块**：只依赖标准库，不得依赖 config / ffmpeg / UI。
"""

import re
import unicodedata
from pathlib import Path

# 字幕段落的最短显示时长（秒）：识别结果偶有 start≈end 的碎片，直接写出会闪一下
MIN_CUE_SECONDS = 0.2


def _fmt_timecode(seconds: float, sep: str = ",") -> str:
    """秒 → ``HH:MM:SS<sep>mmm``。

    SRT 用逗号分隔毫秒（``00:00:01,500``），WebVTT 用点号（``00:00:01.500``），
    其余部分完全一致，因此两种格式共用这一个格式化函数。
    """
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(total_ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def format_timestamp(seconds: float) -> str:
    """SRT 时间码（毫秒用逗号分隔）。"""
    return _fmt_timecode(seconds, ",")


def char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def wrap_subtitle(text: str, limit: int = 42, max_lines: int = 3):
    """按显示宽度折行：中文占 2 宽度，英文占 1，优先在空格处断开。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if display_width(text) <= limit:
        return [text]
    lines, current, width = [], [], 0
    for ch in text:
        w = char_width(ch)
        if width + w > limit and current:
            line = "".join(current)
            if " " in line:
                head, tail = line.rsplit(" ", 1)
                if head.strip() and tail:
                    lines.append(head.strip())
                    current = list(tail)
                    width = display_width(tail)
                    if ch != " ":
                        current.append(ch)
                        width += w
                    continue
            lines.append(line.strip())
            current = [] if ch == " " else [ch]
            width = 0 if ch == " " else w
        else:
            current.append(ch)
            width += w
    if current:
        lines.append("".join(current).strip())
    return [ln for ln in lines if ln][:max_lines]


def write_srt(segments, path: str) -> None:
    """写出 SRT。序号只对**真正写出**的条目递增，保证 1,2,3… 连续无跳号。"""
    blocks = []
    index = 0
    for seg in segments:
        start = max(0.0, seg["start"])
        end = max(start + MIN_CUE_SECONDS, seg["end"])
        lines = wrap_subtitle(seg["text"])
        if not lines:
            continue
        index += 1
        blocks.append(str(index))
        blocks.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
        blocks.extend(lines)
        blocks.append("")
    Path(path).write_text("\n".join(blocks) + "\n", encoding="utf-8")


def write_vtt(segments, path: str) -> None:
    """写出 WebVTT。

    与 SRT 的差异只在格式要求：首行固定 ``WEBVTT`` 后接空行、时间码毫秒用
    点号、序号可省略（这里一律不写）。折行规则、空段跳过与最短时长保护与
    SRT 完全一致。
    """
    blocks = ["WEBVTT", ""]
    for seg in segments:
        start = max(0.0, seg["start"])
        end = max(start + MIN_CUE_SECONDS, seg["end"])
        lines = wrap_subtitle(seg["text"])
        if not lines:
            continue
        blocks.append(
            f"{_fmt_timecode(start, '.')} --> {_fmt_timecode(end, '.')}")
        blocks.extend(lines)
        blocks.append("")
    Path(path).write_text("\n".join(blocks) + "\n", encoding="utf-8")


def _is_cjk(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def write_txt(segments, path: str) -> None:
    parts = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if parts and not (_is_cjk(parts[-1][-1]) or _is_cjk(text[0])):
            parts.append(" ")
        parts.append(text)
    Path(path).write_text("".join(parts) + "\n", encoding="utf-8")
