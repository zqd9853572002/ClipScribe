# -*- coding: utf-8 -*-
"""ffmpeg 模块：时长解析、唯一路径、滤镜构造、封装产物可播放性、硬字幕烧录。"""

import os
import re
import subprocess

import pytest

from clipscribe import ffmpeg as fm


def test_ffmpeg_info_for_usable_binary(ffmpeg_path):
    info = fm.ffmpeg_info(ffmpeg_path)
    assert info is not None
    assert info["libx264"] is True and info["aac"] is True
    assert info["version"]


def test_ffmpeg_info_invalid_path():
    assert fm.ffmpeg_info("") is None
    assert fm.ffmpeg_info(r"C:\definitely\missing\ffmpeg.exe") is None


def test_run_quiet_never_raises():
    assert fm.run_quiet([r"C:\definitely\missing\ffmpeg.exe", "-version"], timeout=5) is None


def test_probe_duration_three_second_clip(ffmpeg_path, sine_audio):
    duration = fm.probe_duration(ffmpeg_path, sine_audio)
    assert 2.9 <= duration <= 3.1


def test_probe_duration_missing_file(ffmpeg_path, tmp_path):
    assert fm.probe_duration(ffmpeg_path, str(tmp_path / "nope.mp3")) == 0.0


def test_unique_path_increments(tmp_path):
    target = str(tmp_path / "a.mp4")
    assert fm.unique_path(target) == target

    open(target, "wb").close()
    assert fm.unique_path(target) == str(tmp_path / "a (1).mp4")

    open(str(tmp_path / "a (1).mp4"), "wb").close()
    assert fm.unique_path(target) == str(tmp_path / "a (2).mp4")

    open(str(tmp_path / "a (2).mp4"), "wb").close()
    assert fm.unique_path(target) == str(tmp_path / "a (3).mp4")


@pytest.mark.parametrize("mode", ["orig", "1080p", "720p"])
def test_build_video_filter_non_empty(mode):
    expr = fm.build_video_filter(mode)
    assert expr
    assert "yuv420p" in expr


def test_build_video_filter_targets():
    assert "scale=1920:1080" in fm.build_video_filter("1080p")
    assert "scale=1280:720" in fm.build_video_filter("720p")
    assert "trunc(iw/2)*2" in fm.build_video_filter("orig")


def test_filter_escape_path():
    # 用中性占位用户名，避免把本机真实路径写进仓库
    assert fm.filter_escape_path(r"C:\Users\user\bd.rnnn") == "C\\:/Users/user/bd.rnnn"


def test_build_convert_cmd_with_loudnorm():
    cmd = fm.build_convert_cmd("ffmpeg", "a.mp3", "c.png", "o.mp4", "720p",
                               loudnorm=True)
    assert "-af" in cmd
    filter_expr = cmd[cmd.index("-af") + 1]
    assert filter_expr == "loudnorm=I=-16:TP=-1.5:LRA=11"


def test_build_convert_cmd_loudnorm_limits_duration():
    """单遍 loudnorm 会缓冲，必须显式 -t 才能让循环封面按时结束。"""
    cmd = fm.build_convert_cmd("ffmpeg", "a.mp3", "c.png", "o.mp4", "720p",
                               loudnorm=True, duration=3.0)
    assert "-t" in cmd
    assert cmd[cmd.index("-t") + 1] == "3.000"


def test_build_convert_cmd_without_loudnorm():
    cmd = fm.build_convert_cmd("ffmpeg", "a.mp3", "c.png", "o.mp4", "720p",
                               loudnorm=False)
    assert "-af" not in cmd
    assert not any("loudnorm" in part for part in cmd)
    # 基础命令仍是「封面 + 音轨」的 1fps 静态图链路
    assert "-vf" in cmd and "-c:v" in cmd and "libx264" in cmd


@pytest.mark.integration
def test_convert_one_produces_playable_mp4(ffmpeg_path, sine_audio, black_png, tmp_path):
    out_path = str(tmp_path / "out.mp4")
    progress = []

    rc, err = fm.convert_one(
        ffmpeg_path, sine_audio, black_png, out_path, "720p", 3.0,
        on_progress=progress.append, should_stop=lambda: False)

    assert rc == 0, err
    assert os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    # 产物可被 ffmpeg 正常解析，且时长与源音频一致
    assert 2.5 <= fm.probe_duration(ffmpeg_path, out_path) <= 3.6


# ==================== libass / subtitles 滤镜检测 ====================
FILTERS_WITH_SUBTITLES = """\
Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
  A = Audio input/output
  V = Video input/output
  T. asubcut           A->A       Cut audio at the beginning.
  .. ass               V->V       Render ASS subtitles onto input video using the libass library.
  .. subtitles         V->V       Render text subtitles onto input video using the libass library.
  T. vidstabdetect     V->V       Extract relative transformations, pass 1 of 2.
"""

FILTERS_WITHOUT_SUBTITLES = """\
Filters:
  T. scale             V->V       Scale the input video size and/or convert the image format.
  .. pad               V->V       Pad the input video.
  .. metadata          V->V       Manipulate video frame metadata (no libass here).
"""


def test_has_filter_parses_real_filters_layout():
    assert fm.has_filter(FILTERS_WITH_SUBTITLES, "subtitles") is True
    assert fm.has_filter(FILTERS_WITH_SUBTITLES, "ass") is True
    assert fm.has_filter(FILTERS_WITHOUT_SUBTITLES, "subtitles") is False
    # 只在描述文字里出现不算命中
    assert fm.has_filter(FILTERS_WITHOUT_SUBTITLES, "libass") is False
    # 空文本 / 空名字都不得抛异常
    assert fm.has_filter("", "subtitles") is False
    assert fm.has_filter(FILTERS_WITH_SUBTITLES, "") is False


def test_ffmpeg_info_reports_subtitles_capability(ffmpeg_path):
    """`subtitles` 是可选能力：字段必须存在且为布尔，来源是 `ffmpeg -filters`。"""
    info = fm.ffmpeg_info(ffmpeg_path)
    assert "subtitles" in info
    assert isinstance(info["subtitles"], bool)

    raw = fm.run_quiet([ffmpeg_path, "-hide_banner", "-filters"], timeout=20)
    text = ((raw.stdout or "") + (raw.stderr or "")) if raw else ""
    # 独立复核：只看「第二列就是 subtitles」的行（描述文字里出现不算）
    columns = [line.split() for line in text.splitlines()]
    expected = any(len(parts) > 1 and parts[1] == "subtitles" for parts in columns)
    assert info["subtitles"] is expected


def test_missing_libass_never_rejects_engine(monkeypatch):
    """缺少 libass 的 ffmpeg 不得进入「被跳过」列表：它不是必需能力。"""
    monkeypatch.setattr(
        fm, "ffmpeg_info",
        lambda path: {"path": path, "version": "ffmpeg version 9",
                      "libx264": True, "aac": True, "subtitles": False})
    monkeypatch.setattr(fm, "ffmpeg_candidates", lambda saved=None: ["C:/f/bin/ffmpeg.exe"])

    usable, rejected = fm.discover_ffmpeg()
    assert [item["path"] for item in usable] == ["C:/f/bin/ffmpeg.exe"]
    assert rejected == []


def test_missing_encoder_still_rejects_engine(monkeypatch):
    """对照：缺少必需的 libx264 仍会被跳过（可选能力没有放松必需能力）。"""
    monkeypatch.setattr(
        fm, "ffmpeg_info",
        lambda path: {"path": path, "version": "ffmpeg version 9",
                      "libx264": False, "aac": True, "subtitles": True})
    monkeypatch.setattr(fm, "ffmpeg_candidates", lambda saved=None: ["C:/f/bin/ffmpeg.exe"])

    usable, rejected = fm.discover_ffmpeg()
    assert usable == []
    assert len(rejected) == 1


# ==================== 烧录滤镜链 / force_style ====================
def test_build_video_filter_without_burn_has_no_subtitles():
    for mode in ("720p", "1080p", "orig"):
        assert "subtitles=" not in fm.build_video_filter(mode)


def test_build_video_filter_burns_when_sub_name_given():
    expr = fm.build_video_filter("720p", sub_name="sub.srt",
                                 font_name="Microsoft YaHei")
    assert "subtitles=sub.srt:force_style='" in expr
    assert "FontName=Microsoft YaHei" in expr
    assert expr.endswith("'"), "force_style 必须用单引号包住，否则逗号会被当成滤镜分隔符"


@pytest.mark.parametrize("mode", ["720p", "1080p", "orig"])
def test_subtitles_filter_is_appended_after_scale_pad(mode):
    """subtitles 必须在 scale/pad/format 之后，字号才是输出像素。"""
    expr = fm.build_video_filter(mode, sub_name="sub.srt")
    sub_at = expr.index("subtitles=")
    assert sub_at > expr.index("scale=")
    assert sub_at > expr.index("format=yuv420p")
    if mode != "orig":
        assert sub_at > expr.index("pad=")
        assert sub_at > expr.index("setsar=1")


@pytest.mark.parametrize("mode,height", [("720p", 720), ("1080p", 1080)])
def test_force_style_follows_output_height(mode, height):
    style = fm.burn_style(height, "Microsoft YaHei")
    assert fm.output_height(mode) == height
    assert f"FontSize={round(height * fm.BURN_SIZE_RATIO)}" in style
    assert f"MarginV={round(height * fm.BURN_MARGIN_RATIO)}" in style
    assert "Outline=2" in style and "Shadow=0" in style


def test_force_style_font_size_differs_between_720p_and_1080p():
    small = fm.burn_style(fm.output_height("720p"))
    large = fm.burn_style(fm.output_height("1080p"))
    assert small != large
    assert "FontSize=22" in small      # round(720 * 0.03)
    assert "FontSize=32" in large      # round(1080 * 0.03)


def test_force_style_clamps_extreme_heights():
    tiny = fm.burn_style(100)
    assert "FontSize=16" in tiny and "MarginV=10" in tiny
    huge = fm.burn_style(4000)
    assert "FontSize=48" in huge and "MarginV=80" in huge


def test_force_style_omits_font_name_when_unknown():
    """本机没有中文字体时不得写死 FontName，交给 libass 自行回退。"""
    style = fm.burn_style(1080, "")
    assert "FontName" not in style
    assert "FontSize=32" in style


def test_orig_mode_uses_default_burn_height():
    assert fm.output_height("orig") == fm.DEFAULT_BURN_HEIGHT
    assert "subtitles=" in fm.build_video_filter("orig", sub_name="sub.srt")


# ==================== 字体探测 ====================
def test_detect_cjk_font_prefers_yahei(tmp_path):
    (tmp_path / "msyh.ttc").write_bytes(b"")
    (tmp_path / "NotoSansCJK-Regular.ttc").write_bytes(b"")
    assert fm.detect_cjk_font([str(tmp_path)]) == "Microsoft YaHei"


def test_detect_cjk_font_falls_back_to_noto(tmp_path):
    (tmp_path / "NotoSansCJK-Regular.ttc").write_bytes(b"")
    assert fm.detect_cjk_font([str(tmp_path)]) == "Noto Sans CJK SC"


def test_detect_cjk_font_returns_empty_when_absent(tmp_path):
    assert fm.detect_cjk_font([str(tmp_path)]) == ""
    assert fm.detect_cjk_font([str(tmp_path / "missing")]) == ""


def test_font_dirs_cover_windows_fonts(monkeypatch):
    monkeypatch.setenv("WINDIR", r"C:\Windows")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\user\AppData\Local")
    dirs = fm.font_dirs()
    assert dirs[0] == os.path.join(r"C:\Windows", "Fonts")
    assert any(path.endswith(os.path.join("Microsoft", "Windows", "Fonts"))
               for path in dirs)


# ==================== 命令构造 / 真实烧录 ====================
def test_burn_keeps_duration_limit_and_shortest():
    """烧录场景下 `-t` 与 `-shortest` 必须保留（loudnorm 的缓冲问题依旧存在）。"""
    cmd = fm.build_convert_cmd("ffmpeg", "a.mp3", "c.png", "o.mp4", "720p",
                               loudnorm=True, duration=3.0, sub_name="sub.srt")
    assert cmd.index("-t") > 0 and cmd[cmd.index("-t") + 1] == "3.000"
    assert "-shortest" in cmd
    assert "subtitles=sub.srt" in cmd[cmd.index("-vf") + 1]


def test_build_convert_cmd_without_burn_is_unchanged():
    plain = fm.build_convert_cmd("ffmpeg", "a.mp3", "c.png", "o.mp4", "720p")
    assert not any("subtitles" in part for part in plain)


def _frame_luma(ffmpeg, video_path, frame=0):
    """返回指定帧的 (YAVG, YMAX)，用于判断画面里是否真的出现了字幕像素。"""
    res = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "info", "-i", video_path,
         "-vf", f"select=eq(n\\,{frame}),signalstats,metadata=print",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True, creationflags=fm.NO_WINDOW)
    text = (res.stdout or "") + (res.stderr or "")
    avg = re.search(r"YAVG=([\d.]+)", text)
    top = re.search(r"YMAX=(\d+)", text)
    return (float(avg.group(1)) if avg else 0.0), (int(top.group(1)) if top else 0)


@pytest.mark.integration
def test_convert_one_burns_subtitles_from_chinese_path(ffmpeg_path, sine_audio,
                                                        black_png, tmp_path):
    """中文 + 空格路径的 SRT 也能烧录：靠临时 ASCII 目录 + 子进程 cwd 绕开。"""
    sub_dir = tmp_path / "字幕 测试"
    sub_dir.mkdir()
    srt = sub_dir / "中文字幕.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,500\nHello 世界 hard subs\n",
                   encoding="utf-8")

    plain = str(tmp_path / "plain.mp4")
    burned = str(tmp_path / "burned.mp4")

    rc, err = fm.convert_one(ffmpeg_path, sine_audio, black_png, plain, "720p", 3.0,
                             on_progress=lambda _p: None, should_stop=lambda: False)
    assert rc == 0, err
    rc, err = fm.convert_one(ffmpeg_path, sine_audio, black_png, burned, "720p", 3.0,
                             on_progress=lambda _p: None, should_stop=lambda: False,
                             sub_path=str(srt), font_name="Microsoft YaHei")
    assert rc == 0, err

    assert os.path.isfile(burned) and os.path.getsize(burned) > 0
    assert 2.5 <= fm.probe_duration(ffmpeg_path, burned) <= 3.6
    plain_avg, plain_max = _frame_luma(ffmpeg_path, plain)
    burned_avg, burned_max = _frame_luma(ffmpeg_path, burned)
    # 字幕真的进画面了：亮度均值上升，且出现更亮的像素
    assert burned_avg > plain_avg, (plain_avg, burned_avg)
    assert burned_max > plain_max


@pytest.mark.integration
def test_convert_one_falls_back_when_subtitle_missing(ffmpeg_path, sine_audio,
                                                       black_png, tmp_path):
    """字幕文件读不到时退回普通封装：批量任务不能因为一个字幕文件中断。"""
    out_path = str(tmp_path / "fallback.mp4")
    rc, err = fm.convert_one(
        ffmpeg_path, sine_audio, black_png, out_path, "720p", 3.0,
        on_progress=lambda _p: None, should_stop=lambda: False,
        sub_path=str(tmp_path / "字幕 测试" / "nope.srt"))
    assert rc == 0, err
    assert os.path.isfile(out_path)
