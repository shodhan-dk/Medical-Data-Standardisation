# Veritas Claims Standardization Pipeline

This repository contains a Python-based claims-document processing pipeline for ingesting, standardizing, validating, and reviewing clinical records. It is designed for operational use and includes both a command-line entry point and a Streamlit dashboard for reviewing processed data.

## What the project does

- Ingests clinic JSON documents from a folder such as [sample-data](sample-data)
- Extracts and standardizes record-level fields for discharge summaries and lab reports
- Applies deduplication and lab-result analytics/flagging
- Stores structured output in a SQLite database at [veritas_claims.db](veritas_claims.db)
- Exposes an operational UI for reviewing records, flagged results, and clinic-level summaries

## Project structure

- [config](config) — normalization maps for test names, units, medicine names, and reference ranges
- [docs](docs) — design and architecture notes
- [sample-data](sample-data) — example input files for local testing
- [src](src) — pipeline implementation, database logic, validation, and UI
- [tests](tests) — project test area

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

This will process the sample files and write output to [veritas_claims.db](veritas_claims.db).

### 4. Launch the operational UI

```powershell
streamlit run src/ui.py
```

The UI provides four tabs:

- Dashboard
- Flagged Records
- Record Inspector
- Clinic Summary

## Output and data model

The pipeline writes data into SQLite tables including:

- records
- lab_results
- medications
- dead_letters
- pipeline_runs

These tables support both CLI-based review and UI-based operations.

## Notes

- The normalization behavior is driven by configuration files in [config](config)
- The sample data can be replaced with your own JSON files by pointing the input folder to a different directory
- Re-running the pipeline against the same input is idempotent and refreshes existing records rather than duplicating them
