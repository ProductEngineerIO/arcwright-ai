"""Core IO — YAML and async text I/O primitives.

Strict scope: YAML pair + async text pair.  No JSONL, no markdown, no domain logic.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import yaml

from arcwright_ai.core.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = [
    "load_yaml",
    "read_text_async",
    "save_yaml",
    "write_text_async",
]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML content as a dict.  An empty file returns ``{}``.

    Raises:
        ConfigError: If the file cannot be read or contains invalid YAML.
    """
    try:
        content = path.read_text(encoding="utf-8")
        result = yaml.safe_load(content)
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise ConfigError(
                f"Expected a YAML mapping at {path}, got {type(result).__name__}",
                details={"path": str(path)},
            )
        return result
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Invalid YAML in {path}: {exc}",
            details={"path": str(path)},
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"Cannot read {path}: {exc}",
            details={"path": str(path)},
        ) from exc


def save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write data as a YAML file.

    Args:
        path: Destination :class:`~pathlib.Path`.
        data: Data to serialise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


async def read_text_async(path: Path) -> str:
    """Read a text file asynchronously.

    Args:
        path: Path to the file.

    Returns:
        File contents as a string.
    """
    return await asyncio.to_thread(path.read_text, encoding="utf-8")


async def write_text_async(path: Path, content: str) -> None:
    """Write text to a file asynchronously.

    Args:
        path: Destination path.  Parent directories must exist.
        content: Text to write.
    """
    await asyncio.to_thread(path.write_text, content, encoding="utf-8")
