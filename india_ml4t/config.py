"""Path configuration for the India extension."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INDIA_DATA_DIR = Path("D:/ML4T_data")
DEFAULT_BACKUP_DIRS: tuple[Path, ...] = (
    Path("C:/ML4T/backups"),
    Path("D:/ML4T_BACKUPS"),
    Path("E:/ML4T_backups"),
)


@dataclass(frozen=True)
class StudioPaths:
    repo_root: Path
    data_dir: Path
    backup_dirs: tuple[Path, ...]


def get_studio_paths(repo_root: Path | None = None) -> StudioPaths:
    root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
    env_data = os.environ.get("ML4T_DATA_PATH", "").strip()
    data_dir = (
        Path(env_data).expanduser().resolve() if env_data else DEFAULT_INDIA_DATA_DIR.resolve()
    )
    return StudioPaths(root, data_dir, DEFAULT_BACKUP_DIRS)
