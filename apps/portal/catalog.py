"""Discover the book chapters, notebooks and case-study stages safely."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_CHAPTER_RE = re.compile(r"^(?P<number>\d{2})_(?P<slug>.+)$")
_STAGE_RE = re.compile(r"^\d+[a-z]?_.+\.py$", re.IGNORECASE)


@dataclass(frozen=True)
class Chapter:
    number: int
    slug: str
    title: str
    path: str
    readme: str | None
    notebook_count: int


@dataclass(frozen=True)
class Notebook:
    title: str
    path: str
    source_path: str | None


@dataclass(frozen=True)
class CaseStudy:
    slug: str
    title: str
    path: str
    readme: str
    stage_paths: tuple[str, ...]


def _display_title(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def discover_chapters(root: Path = REPO_ROOT) -> list[Chapter]:
    """Return numbered book chapters found in the repository."""
    chapters: list[Chapter] = []
    for folder in sorted(root.iterdir()):
        match = _CHAPTER_RE.match(folder.name)
        if not folder.is_dir() or match is None:
            continue
        notebooks = [
            path
            for path in folder.rglob("*.ipynb")
            if ".ipynb_checkpoints" not in path.parts
            and not any(part.startswith(".") for part in path.parts)
        ]
        readme_path = folder / "README.md"
        chapters.append(
            Chapter(
                number=int(match.group("number")),
                slug=folder.name,
                title=_display_title(match.group("slug")),
                path=folder.relative_to(root).as_posix(),
                readme=readme_path.relative_to(root).as_posix() if readme_path.is_file() else None,
                notebook_count=len(notebooks),
            )
        )
    return sorted(chapters, key=lambda item: item.number)


def list_chapter_notebooks(chapter: Chapter, root: Path = REPO_ROOT) -> list[Notebook]:
    """List generated notebook views and their paired Jupytext Python sources."""
    folder = root / chapter.path
    notebooks: list[Notebook] = []
    for path in sorted(folder.rglob("*.ipynb")):
        if ".ipynb_checkpoints" in path.parts or not _inside_root(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        source = path.with_suffix(".py")
        source_relative = (
            source.relative_to(root).as_posix()
            if source.is_file() and _inside_root(source, root)
            else None
        )
        notebooks.append(
            Notebook(
                title=path.stem.replace("_", " ").replace("-", " ").title(),
                path=relative,
                source_path=source_relative,
            )
        )
    return notebooks


def discover_case_studies(root: Path = REPO_ROOT) -> list[CaseStudy]:
    """Find case-study folders containing an overview and numbered Python stages."""
    base = root / "case_studies"
    if not base.is_dir():
        return []

    studies: list[CaseStudy] = []
    for folder in sorted(base.iterdir()):
        readme = folder / "README.md"
        if not folder.is_dir() or not readme.is_file():
            continue
        stages = tuple(
            path.relative_to(root).as_posix()
            for path in sorted(folder.glob("*.py"))
            if _STAGE_RE.match(path.name) and _inside_root(path, root)
        )
        if not stages:
            continue
        studies.append(
            CaseStudy(
                slug=folder.name,
                title=_display_title(folder.name),
                path=folder.relative_to(root).as_posix(),
                readme=readme.relative_to(root).as_posix(),
                stage_paths=stages,
            )
        )
    return studies


def resolve_chapter_notebook(relative_path: str, root: Path = REPO_ROOT) -> Path:
    """Resolve a notebook only when it belongs to a discovered numbered chapter."""
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.suffix.lower() != ".ipynb":
        raise ValueError("Only repository chapter notebooks can be executed.")
    chapters = {chapter.path: chapter for chapter in discover_chapters(root)}
    if not candidate.parts or candidate.parts[0] not in chapters:
        raise ValueError("The selected file is not inside a recognised book chapter.")
    resolved = root / candidate
    if not resolved.is_file() or not _inside_root(resolved, root):
        raise ValueError("The selected notebook does not exist inside this repository.")
    allowed = {item.path for item in list_chapter_notebooks(chapters[candidate.parts[0]], root)}
    if candidate.as_posix() not in allowed:
        raise ValueError("The selected notebook is not in the chapter catalogue.")
    return resolved.resolve()


def resolve_case_study_stage(relative_path: str, root: Path = REPO_ROOT) -> Path:
    """Resolve a Python stage only when it belongs to a discovered case study."""
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.suffix.lower() != ".py":
        raise ValueError("Only case-study Python stages can be executed here.")
    if len(candidate.parts) < 3 or candidate.parts[0] != "case_studies":
        raise ValueError("The selected file is not a case-study stage.")
    studies = {study.slug: study for study in discover_case_studies(root)}
    if (
        candidate.parts[1] not in studies
        or candidate.as_posix() not in studies[candidate.parts[1]].stage_paths
    ):
        raise ValueError("The selected stage is not in the case-study catalogue.")
    resolved = root / candidate
    if not resolved.is_file() or not _inside_root(resolved, root):
        raise ValueError("The selected stage does not exist inside this repository.")
    return resolved.resolve()
