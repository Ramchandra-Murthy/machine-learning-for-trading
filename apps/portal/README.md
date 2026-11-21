# Unified ML4T Streamlit Portal

The portal is a single local interface for the repository's 27 book chapters, nine case
studies, and the India RP2 workstream. It calls the repository's existing Python sources;
it does not replace notebooks, algorithms, configurations, or datasets.

## Deploy to Streamlit Community Cloud

The hosted portal is configured from the repository directly; Docker is not required.

In Streamlit Community Cloud, select:

- Repository: `Ramchandra-Murthy/machine-learning-for-trading`
- Branch: `feat/rp2-nse-data`
- Main file path: `apps/portal/app.py`

The app-specific `apps/portal/requirements.txt` installs the lightweight web runtime. The
India RP2 workspace accepts an NSE `.csv`/`.csv.gz` and a BSE ZIP containing a
`BSE_EQ_SCRIP_*.csv` member, applies one operator-selected as-of date, runs the repository's
parsers and ISIN reconciliation, builds the conservative listing-eligibility output, validates
the six output datasets, and offers them as a CSV ZIP download. Uploads are limited to 25 MB
per source and the selected expanded BSE CSV member is limited to 80 MB.

The Cloud dependency set is not the complete ML4T research environment. Chapter notebooks and
case-study stages may need additional Python packages, datasets, credentials, GPU/database
services, and published case-study artifacts. The app reports missing prerequisites rather than
claiming that every research pipeline can run in the hosted environment. Trading-permission
mappings that have not been independently verified remain `UNKNOWN`; the UI does not enable
them by user override.

## Start the portal locally with Docker


From the repository root:

    docker compose --profile portal build portal
    docker compose --profile portal up portal

Open http://localhost:8501. The service binds to loopback only and is intended for local use.
The portal image is based on the published ml4t/ml4t:latest runtime, so Docker downloads
that base image when building the portal image.

To stop it, press Ctrl+C in the terminal.

## What is available

- Home: repository coverage and environment checks.
- Book chapters: browse chapter READMEs, inspect the paired Python source, change simple
  Papermill parameters, and execute the selected chapter notebook.
- Case studies: browse the nine stage-based workflows. Create an isolated experiment copy
  and run its Python stages against that copy using ML4T_OUTPUT_DIR; the downloaded release
  artifacts and tracked configuration are not used as the write target.
- India RP2: upload NSE and BSE masters, run the canonical parsers and ISIN reconciliation,
  inspect eligibility/duplicate/exception outputs, validate the export bundle, and download
  six CSV datasets. Unverified trading-permission mappings remain UNKNOWN.

## Execution safeguards

- Only notebook paths discovered inside numbered chapter folders can be launched from the
  chapter runner. Only numbered Python stages discovered inside a case-study folder can be
  launched from the case-study runner.
- Notebook execution is an explicit user action and runs through Papermill, not through a
  browser-side code interpreter.
- Case-study stages require a downloaded run-log artifact bundle. Before execution, the portal
  calls scripts/create_experiment.py and directs writes to a new ignored .streamlit_runs/
  workspace with ML4T_OUTPUT_DIR.
- A stage can still fail when its data, API credentials, GPU, database, or upstream stage
  outputs are unavailable. Run case-study stages in the order shown by that case study's README.
- The portal is not a live-trading terminal. It does not submit orders.

## Local Python installation

The supported repository environment is Python 3.14 and is defined by the root project.
Install Streamlit into that environment, then run:

    uv run --with "streamlit>=1.40,<2" streamlit run apps/portal/app.py

The Docker route is recommended for a consistent environment on Windows.
