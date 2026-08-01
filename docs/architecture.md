# Architecture Description

## Overview
The repository implements a lightweight medical document standardisation pipeline. The solution reads JSON files from the input folder, ingests and parses them, normalises clinical values using configuration maps, validates results, and stores processed data in SQLite for review.

## Main components
- Ingestion layer: discovers input files, parses JSON payloads, and builds normalized envelope objects.
- Standardisation and validation layer: applies rules for age, gender, dates, test-name normalization, unit harmonisation, deduplication, and result analytics.
- Storage layer: persists records, lab results, medications, dead-letter entries, and pipeline run summaries in SQLite.
- Operational UI: provides a dashboard and review views for flagged records, record inspection, and clinic-level summaries.

## Data flow
1. Raw JSON files are placed in the input directory.
2. The ingestion module reads each file and creates structured envelopes.
3. The pipeline processes envelopes into standardized rows and writes them to the database.
4. The Streamlit app loads the database tables and presents them to ops users.

## Design choices
- SQLite is used for the current implementation because it keeps the project easy to run locally and review quickly.
- Configuration files under the config folder decouple normalization logic from code.
- The pipeline is idempotent: rerunning over the same input refreshes existing rows rather than duplicating them.

## Suggested slide content
Use the Draw.io diagram in this folder as the backbone for a short Google Slides deck covering the problem, data flow, core components, assumptions, and next steps.
