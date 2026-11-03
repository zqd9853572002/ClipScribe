# -*- coding: utf-8 -*-
"""ffmpeg 模块：时长解析、唯一路径、滤镜构造、封装产物可播放性。"""

import os

import pytest

from mp3tom4 import ffmpeg as fm


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
