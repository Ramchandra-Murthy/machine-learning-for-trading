from pathlib import Path

import pytest

from apps.portal.catalog import (
    REPO_ROOT,
    discover_case_studies,
    discover_chapters,
    list_chapter_notebooks,
    resolve_case_study_stage,
    resolve_chapter_notebook,
)


def test_catalog_discovers_all_book_chapters() -> None:
    chapters = discover_chapters()
    assert len(chapters) == 27
    assert [chapter.number for chapter in chapters] == list(range(1, 28))
    assert chapters[0].slug == "01_process_is_edge"


def test_catalog_discovers_nine_case_studies() -> None:
    studies = discover_case_studies()
    assert len(studies) == 9
    assert all(study.stage_paths for study in studies)


def test_chapter_notebook_resolver_accepts_catalogued_notebook() -> None:
    chapter = discover_chapters()[0]
    notebook = list_chapter_notebooks(chapter)[0]
    resolved = resolve_chapter_notebook(notebook.path)
    assert resolved.is_file()
    assert resolved.suffix == ".ipynb"
    assert resolved.is_relative_to(REPO_ROOT)


def test_chapter_notebook_resolver_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        resolve_chapter_notebook("../pyproject.toml")


def test_case_study_resolver_accepts_catalogued_stage() -> None:
    study = discover_case_studies()[0]
    resolved = resolve_case_study_stage(study.stage_paths[0])
    assert resolved.is_file()
    assert resolved.suffix == ".py"


def test_case_study_resolver_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        resolve_case_study_stage("../pyproject.toml")
