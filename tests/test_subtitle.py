# -*- coding: utf-8 -*-
"""subtitle 模块：时间戳边界、中英混排折行、SRT/TXT 内容与重名唯一路径。"""

from clipscribe import subtitle as st
from clipscribe.ffmpeg import unique_path


# ---------- format_timestamp ----------
def test_format_timestamp_zero():
    assert st.format_timestamp(0) == "00:00:00,000"


def test_format_timestamp_whole_second():
    assert st.format_timestamp(1) == "00:00:01,000"
    assert st.format_timestamp(59) == "00:00:59,000"


def test_format_timestamp_millisecond_carry():
    # 59999.6ms 四舍五入后应进位到整分钟
    assert st.format_timestamp(59.9996) == "00:01:00,000"
    assert st.format_timestamp(0.9996) == "00:00:01,000"


def test_format_timestamp_hours():
    assert st.format_timestamp(3661.5) == "01:01:01,500"
    assert st.format_timestamp(3600) == "01:00:00,000"


def test_format_timestamp_negative_clamped():
    assert st.format_timestamp(-5) == "00:00:00,000"


# ---------- 折行 ----------
def test_wrap_subtitle_empty():
    assert st.wrap_subtitle("") == []
    assert st.wrap_subtitle(None) == []
    assert st.wrap_subtitle("   ") == []


def test_wrap_subtitle_short_line_untouched():
    assert st.wrap_subtitle("Hello world") == ["Hello world"]
    assert st.wrap_subtitle("中英 mixed 短句", limit=42) == ["中英 mixed 短句"]


def test_wrap_subtitle_english_wraps_at_spaces():
    lines = st.wrap_subtitle("word " * 20, limit=42)
    assert len(lines) >= 2
    assert all(st.display_width(line) <= 42 for line in lines)
    assert "word" in lines[0]


def test_wrap_subtitle_cjk_counts_double_width():
    lines = st.wrap_subtitle("中" * 60, limit=42)
    assert len(lines) >= 2
    assert all(st.display_width(line) <= 42 for line in lines)
    # 中文每字宽 2，42 宽度最多容纳 21 个汉字
    assert len(lines[0]) == 21


def test_wrap_subtitle_max_lines_cap():
    lines = st.wrap_subtitle("中" * 200, limit=10, max_lines=2)
    assert len(lines) == 2


# ---------- SRT ----------
def test_write_srt_content(tmp_path):
    segments = [
        {"start": 0.0, "end": 1.0, "text": "你好世界"},
        {"start": 2.0, "end": 2.5, "text": "hello"},
    ]
    path = tmp_path / "a.srt"
    st.write_srt(segments, str(path))

    assert path.read_text(encoding="utf-8") == (
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "你好世界\n"
        "\n"
        "2\n"
        "00:00:02,000 --> 00:00:02,500\n"
        "hello\n"
        "\n"
    )


def test_write_srt_min_end_guard():
    """end 至少为 start + 0.2 秒（既有行为）。"""
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="srt_guard_"))
    path = tmp / "b.srt"
    st.write_srt([{"start": 1.0, "end": 1.01, "text": "x"}], str(path))
    content = path.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:01,200" in content


def test_write_srt_skips_blank_text(tmp_path):
    path = tmp_path / "empty.srt"
    st.write_srt([{"start": 0.0, "end": 1.0, "text": ""}], str(path))
    assert path.read_text(encoding="utf-8") == "\n"


def test_write_srt_numbering_is_continuous(tmp_path):
    """空文本段被跳过时，序号必须仍然从 1 连续递增（不能跳号）。"""
    segments = [
        {"start": 0.0, "end": 1.0, "text": "first"},
        {"start": 1.0, "end": 2.0, "text": "   "},   # 折行后为空 → 跳过
        {"start": 2.0, "end": 3.0, "text": "second"},
        {"start": 3.0, "end": 4.0, "text": ""},      # 同样跳过
        {"start": 4.0, "end": 5.0, "text": "third"},
    ]
    path = tmp_path / "continuous.srt"
    st.write_srt(segments, str(path))

    content = path.read_text(encoding="utf-8")
    assert content.startswith("1\n00:00:00,000 --> 00:00:01,000\nfirst\n")
    assert "\n2\n00:00:02,000 --> 00:00:03,000\nsecond\n" in content
    assert "\n3\n00:00:04,000 --> 00:00:05,000\nthird\n" in content
    assert "\n4\n" not in content
    assert [line for line in content.splitlines() if line.isdigit()] == ["1", "2", "3"]


def test_write_srt_duplicate_name_uses_unique_path(tmp_path):
    segments = [{"start": 0.0, "end": 1.0, "text": "你好"}]
    target = str(tmp_path / "a.srt")

    first = unique_path(target)
    st.write_srt(segments, first)
    second = unique_path(target)
    st.write_srt(segments, second)

    assert first == target
    assert second == str(tmp_path / "a (1).srt")
    assert (tmp_path / "a.srt").is_file()
    assert (tmp_path / "a (1).srt").is_file()


# ---------- VTT ----------
def test_write_vtt_header_and_content(tmp_path):
    """首行 WEBVTT + 空行；时间码用点号；不写序号。"""
    segments = [
        {"start": 0.0, "end": 1.0, "text": "你好世界"},
        {"start": 2.0, "end": 2.5, "text": "hello"},
    ]
    path = tmp_path / "a.vtt"
    st.write_vtt(segments, str(path))

    assert path.read_text(encoding="utf-8") == (
        "WEBVTT\n"
        "\n"
        "00:00:00.000 --> 00:00:01.000\n"
        "你好世界\n"
        "\n"
        "00:00:02.000 --> 00:00:02.500\n"
        "hello\n"
        "\n"
    )


def test_write_vtt_uses_dot_milliseconds(tmp_path):
    path = tmp_path / "b.vtt"
    st.write_vtt([{"start": 1.5, "end": 2.75, "text": "x"}], str(path))
    content = path.read_text(encoding="utf-8")

    assert "00:00:01.500 --> 00:00:02.750" in content
    # VTT 不允许 SRT 的逗号写法
    assert "00:00:01,500" not in content


def test_write_vtt_has_no_cue_numbers(tmp_path):
    path = tmp_path / "c.vtt"
    st.write_vtt([{"start": 0.0, "end": 1.0, "text": "one"},
                  {"start": 1.0, "end": 2.0, "text": "two"}], str(path))
    lines = path.read_text(encoding="utf-8").splitlines()

    assert not [line for line in lines if line.strip().isdigit()]


def test_write_vtt_skips_blank_text(tmp_path):
    path = tmp_path / "d.vtt"
    st.write_vtt([{"start": 0.0, "end": 1.0, "text": ""},
                  {"start": 1.0, "end": 2.0, "text": "   "},
                  {"start": 2.0, "end": 3.0, "text": "keep"}], str(path))
    content = path.read_text(encoding="utf-8")

    assert content.count("-->") == 1
    assert "keep" in content


def test_write_vtt_min_end_guard(tmp_path):
    """end 至少为 start + 0.2 秒，与 SRT 一致。"""
    path = tmp_path / "e.vtt"
    st.write_vtt([{"start": 1.0, "end": 1.01, "text": "x"}], str(path))
    assert "00:00:01.000 --> 00:00:01.200" in path.read_text(encoding="utf-8")


def test_write_vtt_wraps_like_srt(tmp_path):
    """折行规则与 SRT 完全相同（42 宽 / 最多 3 行 / CJK 记 2 宽）。"""
    text = "中" * 60
    path = tmp_path / "f.vtt"
    st.write_vtt([{"start": 0.0, "end": 5.0, "text": text}], str(path))
    lines = path.read_text(encoding="utf-8").splitlines()

    body = [line for line in lines if line and "-->" not in line and line != "WEBVTT"]
    assert body == st.wrap_subtitle(text)
    assert all(st.display_width(line) <= 42 for line in body)


def test_write_vtt_empty_segments(tmp_path):
    path = tmp_path / "g.vtt"
    st.write_vtt([], str(path))
    assert path.read_text(encoding="utf-8") == "WEBVTT\n\n"


def test_write_vtt_is_utf8_without_bom(tmp_path):
    path = tmp_path / "h.vtt"
    st.write_vtt([{"start": 0.0, "end": 1.0, "text": "中文"}], str(path))
    raw = path.read_bytes()

    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "中文" in raw.decode("utf-8")


# ---------- TXT ----------
def test_write_txt_english_joined_with_space(tmp_path):
    path = tmp_path / "a.txt"
    st.write_txt([{"text": "hello"}, {"text": "world"}], str(path))
    assert path.read_text(encoding="utf-8") == "hello world\n"


def test_write_txt_cjk_joined_without_space(tmp_path):
    path = tmp_path / "b.txt"
    st.write_txt([{"text": "你好"}, {"text": "世界"}], str(path))
    assert path.read_text(encoding="utf-8") == "你好世界\n"


def test_write_txt_skips_blank_segments(tmp_path):
    path = tmp_path / "c.txt"
    st.write_txt([{"text": " hello "}, {"text": "   "}, {}, {"text": "world"}], str(path))
    assert path.read_text(encoding="utf-8") == "hello world\n"


def test_write_txt_cjk_english_boundary_locked(tmp_path):
    """锁定现有行为：任一侧为 CJK 时不补空格（隐患见交付说明）。"""
    path = tmp_path / "d.txt"
    st.write_txt([{"text": "你好"}, {"text": "world"}], str(path))
    assert path.read_text(encoding="utf-8") == "你好world\n"

    st.write_txt([{"text": "hello"}, {"text": "世界"}], str(path))
    assert path.read_text(encoding="utf-8") == "hello世界\n"


def test_write_txt_empty_segments(tmp_path):
    path = tmp_path / "e.txt"
    st.write_txt([], str(path))
    assert path.read_text(encoding="utf-8") == "\n"
