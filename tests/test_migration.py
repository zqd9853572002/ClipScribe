# -*- coding: utf-8 -*-
r"""配置与模型缓存目录迁移：`%APPDATA%\Mp3ToMp4` → `%APPDATA%\ClipScribe`。

覆盖点：
* 旧目录存在、新目录不存在 → 整体重命名且内容完整；
* 幂等（新目录已存在 / 二次调用）→ 什么都不改；
* 两个目录都不存在 → 不报错、不建目录；
* `os.replace` 失败 → 退回 `shutil.move`；
* 两步都失败 → 不崩溃、继续使用旧目录、状态为 failed；
* 迁移后模型文件路径能正确解析（关键：模型不会被重新下载）。

所有用例只在 `tmp_path` 上操作，绝不动真实的 `%APPDATA%`。
"""

from pathlib import Path

import pytest

from clipscribe import config

LEGACY = config.LEGACY_APP_NAME
NEW = config.APP_NAME

MODEL_REL = Path("models") / "whisper"
MODEL_FILE = MODEL_REL / "model.bin"
MODEL_BYTES = b"fake-whisper-weights" * 64


@pytest.fixture(autouse=True)
def restore_config_state(monkeypatch):
    """迁移会改写模块级的「当前目录名」，每个用例结束后恢复默认状态。"""
    monkeypatch.setattr(config, "_active_app_dir", config.APP_NAME)
    monkeypatch.setattr(config, "_last_migration", (config.MIGRATION_ABSENT, ""))
    yield


def _make_legacy(root: Path) -> Path:
    """造一个假的旧目录：config.json + 一个假的 whisper 模型文件。"""
    old = root / LEGACY
    (old / MODEL_REL).mkdir(parents=True)
    (old / "config.json").write_text('{"size_mode": "720p"}', encoding="utf-8")
    (old / MODEL_FILE).write_bytes(MODEL_BYTES)
    return old


def test_legacy_dir_is_renamed_with_content_intact(tmp_path, monkeypatch):
    root = tmp_path / "appdata"
    old = _make_legacy(root)
    monkeypatch.setenv("APPDATA", str(root))

    status = config.migrate_legacy_config_dir(root)

    assert status == config.MIGRATION_MIGRATED
    assert config.last_migration() == (config.MIGRATION_MIGRATED, "")
    assert not old.exists(), "旧目录应被整体重命名，而不是复制后保留"
    new = root / NEW
    assert (new / "config.json").read_text(encoding="utf-8") == '{"size_mode": "720p"}'
    assert (new / MODEL_FILE).read_bytes() == MODEL_BYTES
    # 生效目录已经切换到新名字
    assert config.active_app_dir_name() == NEW
    assert config.config_file() == new / "config.json"
    assert config.models_root() == new / "models"


def test_second_call_changes_nothing(tmp_path, monkeypatch):
    """幂等：新目录已存在时不再做任何改动（含不覆盖、不合并）。"""
    root = tmp_path / "appdata"
    _make_legacy(root)
    monkeypatch.setenv("APPDATA", str(root))
    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_MIGRATED

    # 加一个标记文件，第二次调用后它必须还在（说明没被覆盖/清空）
    marker = root / NEW / "marker.txt"
    marker.write_text("keep me", encoding="utf-8")

    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_SKIPPED
    assert config.last_migration() == (config.MIGRATION_SKIPPED, "")
    assert marker.read_text(encoding="utf-8") == "keep me"
    assert (root / NEW / MODEL_FILE).read_bytes() == MODEL_BYTES
    assert not (root / LEGACY).exists()


def test_existing_legacy_dir_is_left_untouched_when_new_dir_exists(tmp_path):
    """两个目录同时存在时，以新目录为准，旧目录一律不动。"""
    root = tmp_path / "appdata"
    old = _make_legacy(root)
    (root / NEW).mkdir(parents=True)

    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_SKIPPED
    assert old.is_dir()
    assert (old / MODEL_FILE).read_bytes() == MODEL_BYTES


def test_both_dirs_missing_is_noop(tmp_path):
    root = tmp_path / "appdata"
    root.mkdir()

    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_ABSENT
    assert config.last_migration() == (config.MIGRATION_ABSENT, "")
    assert not (root / NEW).exists()
    assert not (root / LEGACY).exists()
    # 未发现旧目录时使用新目录，后续按需创建
    assert config.active_app_dir_name() == NEW


def test_replace_failure_falls_back_to_shutil_move(tmp_path, monkeypatch):
    """跨盘符 / 占用导致 os.replace 失败时，退回 shutil.move 仍可完成迁移。"""
    root = tmp_path / "appdata"
    _make_legacy(root)

    def boom(*_args, **_kwargs):
        raise OSError("simulated cross-device rename")

    monkeypatch.setattr(config.os, "replace", boom)

    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_MIGRATED
    assert (root / NEW / MODEL_FILE).read_bytes() == MODEL_BYTES
    assert not (root / LEGACY).exists()


def test_total_failure_keeps_legacy_dir_and_never_raises(tmp_path, monkeypatch):
    """两步都失败：不抛异常、不删除旧目录、路径继续指向旧目录。"""
    root = tmp_path / "appdata"
    old = _make_legacy(root)
    monkeypatch.setenv("APPDATA", str(root))

    def boom(*_args, **_kwargs):
        raise PermissionError("simulated locked file")

    monkeypatch.setattr(config.os, "replace", boom)
    monkeypatch.setattr(config.shutil, "move", boom)

    status = config.migrate_legacy_config_dir(root)

    assert status == config.MIGRATION_FAILED
    assert config.last_migration()[0] == config.MIGRATION_FAILED
    assert config.last_migration()[1], "失败时应记录异常原因供日志使用"
    assert old.is_dir(), "迁移失败绝不能删除旧目录"
    assert (old / MODEL_FILE).read_bytes() == MODEL_BYTES
    assert not (root / NEW).exists()
    # 关键：降级为继续使用旧目录，模型不会因此重新下载
    assert config.active_app_dir_name() == LEGACY
    assert config.config_file() == old / "config.json"
    assert config.models_root() == old / "models"


def test_partial_new_dir_is_cleaned_up_on_move_failure(tmp_path, monkeypatch):
    """shutil.move 半途失败留下的半成品新目录必须清掉，避免下次误判已迁移。"""
    root = tmp_path / "appdata"
    old = _make_legacy(root)

    def broken_move(src, dst, *_args, **_kwargs):
        Path(dst).mkdir(parents=True, exist_ok=True)   # 造出半成品
        raise OSError("simulated failure after creating target")

    def boom(*_args, **_kwargs):
        raise OSError("simulated cross-device rename")

    monkeypatch.setattr(config.os, "replace", boom)
    monkeypatch.setattr(config.shutil, "move", broken_move)

    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_FAILED
    assert not (root / NEW).exists()
    assert (old / MODEL_FILE).read_bytes() == MODEL_BYTES


def test_whisper_model_is_found_after_migration(tmp_path, monkeypatch):
    """迁移后 `whisper_model_ready()` 必须仍能命中缓存，否则会重新下载 1.55 GB。"""
    from clipscribe.asr import whisper_model_ready

    root = tmp_path / "appdata"
    old = root / LEGACY
    snapshot = old / MODEL_REL / "models--Systran--faster-whisper-small" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(MODEL_BYTES)
    (old / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(root))

    assert whisper_model_ready("small") is False  # 迁移前指向旧目录，模型在旧目录外

    assert config.migrate_legacy_config_dir(root) == config.MIGRATION_MIGRATED
    assert whisper_model_ready("small") is True
