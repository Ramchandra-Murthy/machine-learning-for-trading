"""RP-1 foundation smoke tests."""

import subprocess
from pathlib import Path

import india_ml4t
import india_ml4t.backtest
import india_ml4t.data
import india_ml4t.features
import india_ml4t.models
from india_ml4t.config import DEFAULT_INDIA_DATA_DIR, get_studio_paths


def test_package_imports_and_baseline_metadata() -> None:
    assert india_ml4t.__version__ == "0.1.0-rp1"
    assert india_ml4t.__baseline_tag__ == "ml4t-rp-000-baseline"
    assert india_ml4t.__baseline_commit__ == "fe08097f3e43fb3dd1511d68613a6a2dd6ff4461"
    assert india_ml4t.data is not None
    assert india_ml4t.features is not None
    assert india_ml4t.models is not None
    assert india_ml4t.backtest is not None


def test_default_data_path_uses_d_drive(monkeypatch) -> None:
    monkeypatch.delenv("ML4T_DATA_PATH", raising=False)
    assert get_studio_paths().data_dir == DEFAULT_INDIA_DATA_DIR.resolve()


def test_env_override_data_path(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "nse_bse_store"
    monkeypatch.setenv("ML4T_DATA_PATH", str(custom))
    assert get_studio_paths().data_dir == custom.resolve()
    assert not custom.exists()


def test_baseline_tag_resolves_to_rp0_commit() -> None:
    paths = get_studio_paths()
    result = subprocess.run(
        ["git", "rev-parse", "ml4t-rp-000-baseline^{}"],
        cwd=paths.repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == india_ml4t.__baseline_commit__
