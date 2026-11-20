"""Controlled execution helpers for repository-owned notebooks and case studies."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nbformat

from apps.portal.catalog import (
    REPO_ROOT,
    resolve_case_study_stage,
    resolve_chapter_notebook,
)

RUNS_DIR = REPO_ROOT / ".streamlit_runs"


@dataclass(frozen=True)
class ExecutionResult:
    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    output_path: str | None = None
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 and not self.timed_out


def _literal_parameters(source: str) -> dict[str, Any]:
    """Extract simple literal assignments from a notebook parameters cell."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    values: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            expression = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            expression = node.value
        else:
            continue
        if expression is None:
            continue
        try:
            value = ast.literal_eval(expression)
        except (ValueError, TypeError, SyntaxError):
            continue
        if not isinstance(value, (str, int, float, bool, type(None))):
            continue
        for target in targets:
            if isinstance(target, ast.Name) and re.fullmatch(r"[A-Za-z_]\w*", target.id):
                values[target.id] = value
    return values


def notebook_parameter_defaults(notebook_path: Path) -> dict[str, Any]:
    """Read only Papermill's explicitly tagged parameters cell."""
    notebook = nbformat.read(notebook_path, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code" and "parameters" in cell.metadata.get("tags", []):
            return _literal_parameters(cell.source)
    return {}


def _base_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("ML4T_DATA_PATH", str(REPO_ROOT / "data"))
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("PLOTLY_RENDERER", "json")
    return env


def _run(
    command: list[str],
    *,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
    output_path: str | None = None,
) -> ExecutionResult:
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env or _base_environment(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ExecutionResult(
            command=tuple(command),
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            output_path=output_path,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return ExecutionResult(
            command=tuple(command),
            return_code=-1,
            stdout=stdout,
            stderr=f"{stderr}\nExecution stopped after {timeout_seconds} seconds.",
            output_path=output_path,
            timed_out=True,
        )


def execute_chapter_notebook(
    relative_path: str,
    *,
    parameters: dict[str, Any] | None = None,
    timeout_seconds: int = 3600,
) -> ExecutionResult:
    """Execute an approved chapter notebook through Papermill."""
    notebook_path = resolve_chapter_notebook(relative_path)
    run_dir = RUNS_DIR / "notebooks" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    output_path = run_dir / f"{notebook_path.stem}.executed.ipynb"

    command = [
        sys.executable,
        "-m",
        "papermill",
        str(notebook_path),
        str(output_path),
        "--cwd",
        str(REPO_ROOT),
        "-k",
        "python3",
        "--log-output",
    ]
    for name, value in (parameters or {}).items():
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError(f"Invalid notebook parameter name: {name!r}")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError(f"Unsupported value type for notebook parameter {name!r}.")
        command.extend(["-p", name, json.dumps(value, ensure_ascii=False)])

    return _run(
        command,
        timeout_seconds=timeout_seconds,
        output_path=str(output_path),
    )


def create_case_study_experiment(case_study: str) -> Path:
    """Create a writable experiment copy before any case-study stage is run."""
    if not re.fullmatch(r"[a-z0-9_]+", case_study):
        raise ValueError("Invalid case-study identifier.")
    source_run_log = REPO_ROOT / "case_studies" / case_study / "run_log"
    if not source_run_log.is_dir() or source_run_log.is_symlink():
        raise FileNotFoundError(
            f"Install the {case_study} case-study artifacts first. "
            f"Run: python scripts/download_artifacts.py --cs {case_study}"
        )

    output_root = RUNS_DIR / "case_studies" / uuid.uuid4().hex
    command = [
        sys.executable,
        "scripts/create_experiment.py",
        "--cs",
        case_study,
        "--output",
        str(output_root),
    ]
    result = _run(command, timeout_seconds=1800)
    if not result.succeeded:
        details = result.stderr.strip() or result.stdout.strip() or "No details returned."
        raise RuntimeError(f"Could not create an isolated experiment:\n{details}")
    return output_root


def execute_case_study_stage(
    relative_path: str,
    *,
    experiment_root: Path,
    timeout_seconds: int = 7200,
) -> ExecutionResult:
    """Run a case-study source stage with ML4T_OUTPUT_DIR pointing at its experiment."""
    stage_path = resolve_case_study_stage(relative_path)
    if not experiment_root.is_dir() or not (experiment_root / stage_path.parent.name).is_dir():
        raise ValueError("The isolated experiment workspace is missing or incomplete.")

    env = _base_environment()
    env["ML4T_OUTPUT_DIR"] = str(experiment_root.resolve())
    command = [sys.executable, str(stage_path)]
    return _run(command, timeout_seconds=timeout_seconds, env=env)
