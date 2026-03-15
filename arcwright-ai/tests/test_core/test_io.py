"""Tests for core/io.py — YAML and async text I/O primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arcwright_ai.core.exceptions import ConfigError
from arcwright_ai.core.io import load_yaml, read_text_async, save_yaml, write_text_async

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# load_yaml / save_yaml round-trip
# ---------------------------------------------------------------------------


def test_load_yaml_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "test.yaml"
    data = {"key": "value", "nested": {"a": 1}}
    save_yaml(p, data)
    loaded = load_yaml(p)
    assert loaded == data


def test_save_yaml_creates_valid_yaml(tmp_path: Path) -> None:
    p = tmp_path / "out.yaml"
    save_yaml(p, {"x": [1, 2, 3]})
    content = p.read_text(encoding="utf-8")
    assert "x:" in content


def test_load_yaml_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    result = load_yaml(p)
    assert result == {}


def test_load_yaml_raises_config_error_on_bad_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("key: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_yaml(p)


def test_load_yaml_raises_config_error_on_non_mapping(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Expected a YAML mapping"):
        load_yaml(p)


def test_load_yaml_raises_config_error_on_missing_file() -> None:
    from pathlib import Path

    p = Path("/nonexistent/path/file.yaml")
    with pytest.raises(ConfigError, match="Cannot read"):
        load_yaml(p)


# ---------------------------------------------------------------------------
# Async text round-trip
# ---------------------------------------------------------------------------


async def test_read_write_text_async_round_trip(tmp_path: Path) -> None:
    content = "Hello, Arcwright!\n"
    p = tmp_path / "test.txt"
    await write_text_async(p, content)
    result = await read_text_async(p)
    assert result == content


async def test_write_text_async_creates_file(tmp_path: Path) -> None:
    p = tmp_path / "created.txt"
    await write_text_async(p, "content")
    assert p.exists()


async def test_read_text_async_returns_all_content(tmp_path: Path) -> None:
    p = tmp_path / "multi.txt"
    text = "line1\nline2\nline3\n"
    p.write_text(text, encoding="utf-8")
    result = await read_text_async(p)
    assert result == text


def test_save_yaml_creates_parent_dirs_if_needed(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dir" / "created.yaml"
    save_yaml(p, {"ok": True})
    assert p.exists()
    assert load_yaml(p) == {"ok": True}


# ---------------------------------------------------------------------------
# load_yaml details attribute in ConfigError
# ---------------------------------------------------------------------------


def test_load_yaml_config_error_has_details_on_bad_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("key: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError) as exc_info:
        load_yaml(p)
    assert exc_info.value.details is not None
    assert "path" in exc_info.value.details


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


def test_all_symbols_exported() -> None:
    import arcwright_ai.core.io as mod

    expected = {"load_yaml", "read_text_async", "save_yaml", "write_text_async"}
    assert set(mod.__all__) == expected
