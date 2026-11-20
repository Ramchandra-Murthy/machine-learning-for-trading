"""Single Streamlit application for book learning, case studies and India RP2."""

from __future__ import annotations

import base64
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import nbformat
import streamlit as st

from apps.portal.catalog import (
    REPO_ROOT,
    discover_case_studies,
    discover_chapters,
    list_chapter_notebooks,
)
from apps.portal.execution import (
    create_case_study_experiment,
    execute_case_study_stage,
    execute_chapter_notebook,
    notebook_parameter_defaults,
)

st.set_page_config(
    page_title="ML4T | Learning & Research Portal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CHAPTERS = discover_chapters(REPO_ROOT)
CASE_STUDIES = discover_case_studies(REPO_ROOT)


def _readme(relative_path: str) -> str:
    path = REPO_ROOT / relative_path
    if not path.is_file():
        return "_No README is available for this section._"
    return path.read_text(encoding="utf-8")


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _show_notebook_outputs(path: Path) -> None:
    """Render common notebook output MIME types without executing embedded HTML."""
    try:
        notebook = nbformat.read(path, as_version=4)
    except Exception as exc:  # noqa: BLE001 - surface malformed execution output
        st.warning(f"Could not read the executed notebook output: {exc}")
        return

    output_count = sum(
        len(cell.get("outputs", []))
        for cell in notebook.cells
        if cell.cell_type == "code"
    )
    st.caption(f"Executed notebook output: {output_count} output items")
    with st.expander("View notebook results", expanded=True):
        rendered = 0
        for cell_index, cell in enumerate(notebook.cells):
            if cell.cell_type != "code":
                continue
            for output in cell.get("outputs", []):
                output_type = output.get("output_type")
                if output_type == "stream":
                    text = output.get("text", "")
                    if text:
                        st.code(text[-12000:], language="text")
                        rendered += 1
                elif output_type == "error":
                    traceback = "\n".join(output.get("traceback", []))
                    st.error(
                        f"Cell {cell_index + 1}: "
                        f"{output.get('ename', 'Error')}: {output.get('evalue', '')}"
                    )
                    if traceback:
                        st.code(traceback[-12000:], language="text")
                    rendered += 1
                elif output_type in {"display_data", "execute_result"}:
                    data = output.get("data", {})
                    if "image/png" in data:
                        st.image(base64.b64decode(data["image/png"]))
                        rendered += 1
                    elif "image/jpeg" in data:
                        st.image(base64.b64decode(data["image/jpeg"]))
                        rendered += 1
                    elif "application/vnd.plotly.v1+json" in data:
                        try:
                            import plotly.io as pio

                            figure = pio.from_json(
                                json.dumps(data["application/vnd.plotly.v1+json"])
                            )
                            st.plotly_chart(figure, use_container_width=True)
                        except Exception as exc:  # noqa: BLE001 - optional renderer path
                            st.info(f"Plotly output could not be displayed: {exc}")
                        rendered += 1
                    elif "text/plain" in data:
                        text = str(data["text/plain"])
                        if text.strip():
                            st.code(text[-12000:], language="text")
                            rendered += 1
        if not rendered:
            st.info("The notebook ran, but it did not produce displayable output cells.")


def _show_result(result: Any, *, notebook: bool = False) -> None:
    if result.succeeded:
        st.success("Execution completed successfully.")
    elif result.timed_out:
        st.error("Execution reached its time limit. Inspect the log before retrying.")
    else:
        st.error(f"Execution failed (exit code {result.return_code}).")

    if result.stdout:
        with st.expander("Execution log", expanded=not result.succeeded):
            st.code(result.stdout[-24000:], language="text")
    if result.stderr:
        with st.expander("Warnings and errors", expanded=not result.succeeded):
            st.code(result.stderr[-24000:], language="text")

    if notebook and result.output_path and Path(result.output_path).is_file():
        _show_notebook_outputs(Path(result.output_path))


def _home() -> None:
    st.title("ML4T Learning & Research Portal")
    st.write(
        "One application for the complete Machine Learning for Trading repository. "
        "Browse the book, execute its chapter notebooks, work through case-study pipelines, "
        "and access the India-market research modules."
    )
    total_notebooks = sum(chapter.notebook_count for chapter in CHAPTERS)
    total_stages = sum(len(study.stage_paths) for study in CASE_STUDIES)
    metrics = st.columns(4)
    metrics[0].metric("Book chapters", len(CHAPTERS))
    metrics[1].metric("Chapter notebooks", total_notebooks)
    metrics[2].metric("Case studies", len(CASE_STUDIES))
    metrics[3].metric("Case-study stages", total_stages)

    st.subheader("Workspaces")
    cards = st.columns(3)
    cards[0].markdown(
        "**Book Library**\n\nRead chapter guides, inspect original Python source, "
        "adjust supported notebook parameters, and run the book examples."
    )
    cards[1].markdown(
        "**Case Study Lab**\n\nExplore nine end-to-end workflows. Create an isolated "
        "experiment and run individual stages without writing into the released baseline."
    )
    cards[2].markdown(
        "**India RP2**\n\nInspect the NSE/BSE security-master, reconciliation, eligibility "
        "and validation components being developed in this repository."
    )

    st.subheader("Runtime")
    runtime = st.columns(3)
    runtime[0].metric("Python", sys.version.split()[0])
    runtime[1].metric("Streamlit", _package_version("streamlit"))
    runtime[2].metric("Papermill", _package_version("papermill"))

    data_path = Path(os.environ.get("ML4T_DATA_PATH", REPO_ROOT / "data"))
    if data_path.exists():
        st.success(f"Data directory found: {data_path}")
    else:
        st.warning(
            f"Data directory not found: {data_path}. Many notebooks require datasets. "
            "Use the repository data guide before running them."
        )


def _book_library() -> None:
    st.title("Book Library")
    if not CHAPTERS:
        st.error("No numbered chapter folders were found.")
        return

    chapter_labels = {
        f"Chapter {item.number:02d} — {item.title} ({item.notebook_count} notebooks)": item
        for item in CHAPTERS
    }
    chapter_label = st.selectbox("Choose a chapter", list(chapter_labels))
    chapter = chapter_labels[chapter_label]

    st.markdown(_readme(chapter.readme) if chapter.readme else "_No chapter guide found._")
    notebooks = list_chapter_notebooks(chapter)
    st.divider()
    st.subheader("Chapter notebooks")
    if not notebooks:
        st.info("This chapter has no notebook files in the repository yet.")
        return

    notebook_labels = {
        f"{item.title} — {item.path}": item for item in notebooks
    }
    selected_label = st.selectbox(
        "Choose a notebook",
        list(notebook_labels),
        key=f"notebook-select-{chapter.slug}",
    )
    selected = notebook_labels[selected_label]
    st.caption(f"Notebook: {selected.path}")

    if selected.source_path:
        with st.expander("Inspect original Python source", expanded=False):
            source = (REPO_ROOT / selected.source_path).read_text(encoding="utf-8")
            st.code(source, language="python", line_numbers=True)
    else:
        st.warning("No paired Jupytext Python source file was found for this notebook.")

    notebook_path = REPO_ROOT / selected.path
    try:
        defaults = notebook_parameter_defaults(notebook_path)
    except Exception as exc:  # noqa: BLE001 - show notebook parsing issue to reader
        defaults = {}
        st.warning(f"Could not read notebook parameters: {exc}")

    st.subheader("Run this chapter notebook")
    st.warning(
        "Running a notebook executes its original Python cells and may take several minutes. "
        "Required datasets, API credentials, and upstream outputs must already be available. "
        "Execution starts only when you press the button."
    )

    parameters: dict[str, Any] = {}
    with st.form(key=f"chapter-run-form-{selected.path}"):
        if defaults:
            st.write("Parameters from the notebook's Papermill parameters cell")
            columns = st.columns(2)
            for index, (name, value) in enumerate(defaults.items()):
                with columns[index % 2]:
                    key = f"param-{selected.path}-{name}"
                    if isinstance(value, bool):
                        parameters[name] = st.checkbox(name, value=value, key=key)
                    elif isinstance(value, int):
                        parameters[name] = st.number_input(
                            name, value=value, step=1, key=key
                        )
                    elif isinstance(value, float):
                        parameters[name] = st.number_input(
                            name, value=value, step=0.1, key=key
                        )
                    elif isinstance(value, str):
                        parameters[name] = st.text_input(name, value=value, key=key)
        else:
            st.caption("This notebook has no simple, editable Papermill parameters.")
        timeout_minutes = st.selectbox(
            "Execution time limit",
            [5, 15, 30, 60, 120],
            index=3,
            format_func=lambda value: f"{value} minutes",
        )
        submitted = st.form_submit_button("Run original notebook", type="primary")

    if submitted:
        with st.spinner("Executing the selected notebook with Papermill..."):
            result = execute_chapter_notebook(
                selected.path,
                parameters=parameters,
                timeout_seconds=int(timeout_minutes * 60),
            )
        st.session_state["last_chapter_result"] = result
        st.session_state["last_chapter_path"] = selected.path

    last_result = st.session_state.get("last_chapter_result")
    if last_result and st.session_state.get("last_chapter_path") == selected.path:
        _show_result(last_result, notebook=True)


def _case_study_lab() -> None:
    st.title("Case Study Lab")
    st.write(
        "The nine case studies are connected research pipelines. Each stage writes artifacts "
        "that later stages consume. Run them in the order documented by the selected case study."
    )
    if not CASE_STUDIES:
        st.error("No case-study folders were found.")
        return

    labels = {
        f"{study.title} ({len(study.stage_paths)} stages)": study
        for study in CASE_STUDIES
    }
    label = st.selectbox("Choose a case study", list(labels))
    study = labels[label]
    st.markdown(_readme(study.readme))

    with st.expander("Pipeline stage catalogue", expanded=True):
        stage_rows = [
            {"Order": index, "Python stage": Path(path).name, "Repository path": path}
            for index, path in enumerate(study.stage_paths, start=1)
        ]
        st.dataframe(stage_rows, use_container_width=True, hide_index=True)

    workspaces = st.session_state.setdefault("case_study_workspaces", {})
    workspace_value = workspaces.get(study.slug)
    source_run_log = REPO_ROOT / study.path / "run_log"

    st.subheader("Isolated experiment")
    st.write(
        "The portal creates a separate writable copy of the case-study configuration and "
        "available generated artifacts. Stage execution points ML4T_OUTPUT_DIR at this copy, "
        "so the downloaded release baseline is not the write destination."
    )
    if not source_run_log.is_dir() or source_run_log.is_symlink():
        st.warning(
            f"The {study.title} artifact bundle is not installed. Download it from the "
            "repository root before creating an experiment:"
        )
        st.code(
            f"python scripts/download_artifacts.py --cs {study.slug}",
            language="bash",
        )
    elif not workspace_value or not Path(workspace_value).is_dir():
        st.warning(
            "Creating an experiment copies the installed run log and configuration. "
            "Some case studies have large artifact bundles and need substantial disk space."
        )
        if st.button("Create isolated experiment", type="primary", key=f"create-{study.slug}"):
            try:
                with st.spinner("Creating the isolated experiment copy..."):
                    experiment_root = create_case_study_experiment(study.slug)
                workspaces[study.slug] = str(experiment_root)
                st.session_state["case_study_workspaces"] = workspaces
                st.success(f"Experiment created: {experiment_root}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001 - show actionable workspace error
                st.error(str(exc))
    else:
        experiment_root = Path(workspace_value)
        st.success(f"Isolated workspace ready: {experiment_root}")
        config_path = experiment_root / study.slug / "config" / "setup.yaml"
        if config_path.is_file():
            with st.expander("View experiment setup.yaml"):
                st.code(config_path.read_text(encoding="utf-8"), language="yaml")

        selected_stage = st.selectbox(
            "Select a stage to run",
            list(study.stage_paths),
            format_func=lambda value: Path(value).name,
            key=f"stage-select-{study.slug}",
        )
        st.warning(
            "Stages may depend on earlier stages, datasets, API keys, GPU support or external "
            "services. Run them in pipeline order. Missing inputs are reported as execution errors."
        )
        timeout_minutes = st.selectbox(
            "Stage time limit",
            [5, 15, 30, 60, 120],
            index=4,
            format_func=lambda value: f"{value} minutes",
            key=f"stage-timeout-{study.slug}",
        )
        if st.button("Run selected Python stage", type="primary", key=f"run-stage-{study.slug}"):
            with st.spinner(f"Running {Path(selected_stage).name} in the experiment..."):
                result = execute_case_study_stage(
                    selected_stage,
                    experiment_root=experiment_root,
                    timeout_seconds=int(timeout_minutes * 60),
                )
            st.session_state["last_case_study_result"] = result
            st.session_state["last_case_study_stage"] = selected_stage

        last_result = st.session_state.get("last_case_study_result")
        if last_result and st.session_state.get("last_case_study_stage") in study.stage_paths:
            _show_result(last_result)


def _india_rp2() -> None:
    st.title("India Markets — RP2")
    st.write(
        "The India RP2 workstream is integrated into this same application as a separate "
        "market-research module. Its data and policy code remains independent of the book's "
        "US-market case-study examples."
    )

    modules = [
        ("NSE security master", "india_ml4t/data/nse_security_master.py"),
        ("BSE security master", "india_ml4t/data/bse_security_master.py"),
        ("ISIN reconciliation", "india_ml4t/data/reconciliation.py"),
        ("Eligibility policy", "india_ml4t/data/eligibility.py"),
        ("Listing eligibility", "india_ml4t/data/listing_eligibility.py"),
        ("Reconciliation exports", "india_ml4t/data/reconciliation_export.py"),
        ("Validation reports", "india_ml4t/data/validation.py"),
    ]
    for name, relative_path in modules:
        path = REPO_ROOT / relative_path
        with st.expander(name):
            if path.is_file():
                st.caption(relative_path)
                st.code(path.read_text(encoding="utf-8"), language="python")
            else:
                st.info(f"Module not present: {relative_path}")

    st.info(
        "The RP2 parser, reconciliation, conservative eligibility, export and validation "
        "modules are present in the repository. Their interactive ingestion and report-running "
        "controls are the next integration step; this page currently provides code inspection."
    )


def _environment() -> None:
    st.title("Environment & Data")
    st.write("The portal uses the repository's Docker-based ML4T runtime.")
    values = {
        "Repository": str(REPO_ROOT),
        "Data path": os.environ.get("ML4T_DATA_PATH", str(REPO_ROOT / "data")),
        "Python": sys.version,
        "Streamlit": _package_version("streamlit"),
        "Papermill": _package_version("papermill"),
        "Notebook format": _package_version("nbformat"),
    }
    st.json(values)
    data_path = Path(values["Data path"])
    st.write("Data directory:", "Available" if data_path.exists() else "Missing")
    if st.button("Refresh environment checks"):
        st.rerun()


def main() -> None:
    st.sidebar.title("ML4T Portal")
    section = st.sidebar.radio(
        "Workspace",
        ["Home", "Book Chapters", "Case Studies", "India RP2", "Environment & Data"],
    )
    st.sidebar.divider()
    st.sidebar.caption("One portal · Original Python code · Shared research workspace")

    if section == "Home":
        _home()
    elif section == "Book Chapters":
        _book_library()
    elif section == "Case Studies":
        _case_study_lab()
    elif section == "India RP2":
        _india_rp2()
    else:
        _environment()


if __name__ == "__main__":
    main()
