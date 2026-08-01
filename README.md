# Medical Data Standardisation

This repository contains a Python-based pipeline for standardising medical and claims-related documents. It ingests JSON records, normalises clinical data, applies validation and deduplication logic, and stores the results in a SQLite database.

## What the project does

- Ingests clinic JSON documents from a folder such as [sample-data](sample-data)
- Extracts and standardises fields for discharge summaries and lab reports
- Applies deduplication and result-flagging logic for lab analytics
- Stores structured output in SQLite tables for records, lab results, medications, dead letters, and pipeline runs
- Provides an operational Streamlit UI for reviewing processed output

## Repository structure

- [config](config) — normalization maps for test names, units, medicine names, and reference ranges
- [docs](docs) — architecture diagram, assumptions, and presentation outline
- [sample-data](sample-data) — example input files for local testing
- [src](src) — pipeline implementation, database logic, validation, and UI
- [tests](tests) — project test area

## Documentation assets

- [docs/architecture.md](docs/architecture.md) — architecture overview and data-flow notes
- [docs/architecture-diagram.drawio](docs/architecture-diagram.drawio) — editable Draw.io diagram for the solution
- [docs/assumptions.md](docs/assumptions.md) — scope, assumptions, and review considerations
- [docs/slide-outline.md](docs/slide-outline.md) — suggested Google Slides structure

## Requirements

This project uses Python 3.10+ and the following packages:

- pandas
- streamlit
- rapidfuzz

## Getting started

### 1. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install pandas streamlit rapidfuzz
```

### 3. Run the pipeline

```powershell
python -m src.main --input sample-data
```

### 4. Launch the operational UI

```powershell
streamlit run src/ui.py
```

The UI provides four tabs:

- Dashboard
- Flagged Records
- Record Inspector
- Clinic Summary

## Notes

- The normalization behaviour is driven by configuration files in [config](config)
- The sample data can be replaced with your own JSON files by pointing the input folder to a different directory
- Re-running the pipeline against the same input is idempotent and refreshes existing records instead of creating duplicates
