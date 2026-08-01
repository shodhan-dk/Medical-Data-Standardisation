"""
Operational UI (FR-5). Run with:  streamlit run src/ui.py

Four tabs map directly to the four FR-5 sub-requirements:
  - Dashboard        -> FR-5.1 Pipeline Dashboard
  - Flagged Records   -> FR-5.3 Flagged Records Review
  - Record Inspector  -> FR-5.2 Record Inspector (raw JSON next to standardized)
  - Clinic Summary     -> FR-5.4 Clinic-level Summary
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st # pyright: ignore[reportMissingImports]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import db  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

st.set_page_config(page_title="Veritas Claims-Pipeline Ops", layout="wide")

DB_PATH = db.DB_PATH
FLAGGED_STATES = {"Outlier", "Invalid", "Above Range", "Below Range"}


@st.cache_data(ttl=2)
def load_table(table: str) -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)
    except pd.errors.DatabaseError:
        return pd.DataFrame()
    finally:
        conn.close()


st.title("🏥 Veritas Claims-Standardization Pipeline")
st.caption("Operational dashboard for ops teams (FR-5)")

with st.sidebar:
    st.header("Run Pipeline")
    input_dir = st.text_input("Input folder", value="sample-data")
    if st.button("▶ Run Pipeline", type="primary", width='stretch'):
        with st.spinner("Processing files..."):
            stats = run_pipeline(input_dir)
        st.success("Pipeline run complete")
        st.json(stats)
        st.cache_data.clear()

    st.divider()
    st.caption(f"Database: `{DB_PATH.name}`")

tab_dash, tab_flagged, tab_inspector, tab_clinic = st.tabs(
    ["📊 Dashboard", "🚩 Flagged Records", "🔍 Record Inspector", "🏥 Clinic Summary"]
)

# ---------------------------------------------------------------------------
# FR-5.1 Pipeline Dashboard
# ---------------------------------------------------------------------------
with tab_dash:
    runs = load_table("pipeline_runs")
    records = load_table("records")
    lab_results = load_table("lab_results")
    dead_letters = load_table("dead_letters")

    if runs.empty:
        st.info("No pipeline runs yet. Click **Run Pipeline** in the sidebar to get started.")
    else:
        latest = runs.sort_values("finished_at", ascending=False).iloc[0]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Files received", int(latest["files_total"]))
        c2.metric("Processed OK", int(latest["files_success"]))
        c3.metric("Failed (dead-letter)", int(latest["files_failed"]))
        c4.metric("Records loaded", int(latest["records_total"]))
        c5.metric("Duplicates suppressed", int(latest["duplicates_suppressed"]))

        flagged_count = int(latest["records_flagged"])
        total_results = len(lab_results) if not lab_results.empty else 1
        flag_rate = flagged_count / max(total_results, 1) * 100
        st.metric("Flagged lab results", flagged_count, delta=f"{flag_rate:.1f}% of all results",
                   delta_color="inverse")

        st.subheader("Run history")
        st.dataframe(
            runs.sort_values("finished_at", ascending=False)[
                ["run_id", "started_at", "finished_at", "files_total", "files_success",
                 "files_failed", "records_total", "records_flagged", "duplicates_suppressed"]
            ],
            width='stretch', hide_index=True,
        )

        if not dead_letters.empty:
            st.subheader("⚠️ Dead-letter queue (malformed files)")
            st.dataframe(dead_letters, width='stretch', hide_index=True)

        if not records.empty:
            st.subheader("Records by type")
            st.bar_chart(records["record_type"].value_counts())

# ---------------------------------------------------------------------------
# FR-5.3 Flagged Records Review
# ---------------------------------------------------------------------------
with tab_flagged:
    lab_results = load_table("lab_results")
    records = load_table("records")

    if lab_results.empty:
        st.info("No lab results yet - run the pipeline first.")
    else:
        flagged = lab_results[lab_results["test_analytics"].isin(FLAGGED_STATES)].copy()
        st.write(f"**{len(flagged)}** flagged results out of {len(lab_results)} total")

        analytics_filter = st.multiselect(
            "Filter by flag type", sorted(FLAGGED_STATES),
            default=sorted(FLAGGED_STATES),
        )
        flagged = flagged[flagged["test_analytics"].isin(analytics_filter)]

        if not records.empty:
            flagged = flagged.merge(
                records[["record_id", "patient_name", "hospital_name", "clinic_id"]],
                on="record_id", how="left",
            )

        display_cols = [c for c in [
            "record_id", "patient_name", "hospital_name", "clinic_id",
            "test_name_original", "test_name_canonical", "result_text_original",
            "result_value", "unit_canonical", "range_text_original",
            "test_analytics", "flag_reason",
        ] if c in flagged.columns]

        st.dataframe(flagged[display_cols], width='stretch', hide_index=True)

# ---------------------------------------------------------------------------
# FR-5.2 Record Inspector-raw JSON next to standardized output
# ---------------------------------------------------------------------------
with tab_inspector:
    records = load_table("records")
    lab_results = load_table("lab_results")
    medications = load_table("medications")

    if records.empty:
        st.info("No records yet-run the pipeline first.")
    else:
        search = st.text_input("Search by patient name, document ID, or record ID")
        filtered = records
        if search:
            mask = (
                records["patient_name"].astype(str).str.contains(search, case=False, na=False)
                | records["document_id"].astype(str).str.contains(search, case=False, na=False)
                | records["record_id"].astype(str).str.contains(search, case=False, na=False)
            )
            filtered = records[mask]

        options = filtered["record_id"].tolist()
        labels = {
            r["record_id"]: f"{r['record_type']}-{r['patient_name']} ({r['record_id'][:8]}…)"
            for _, r in filtered.iterrows()
        }
        chosen = st.selectbox("Select a record", options, format_func=lambda rid: labels.get(rid, rid))

        if chosen:
            row = records[records["record_id"] == chosen].iloc[0]
            col_raw, col_std = st.columns(2)

            with col_raw:
                st.subheader("Raw source (audit trail.FR-4.3)")
                st.caption(f"Source file: `{row['source_file']}`")
                try:
                    raw_json = json.loads(Path(row["source_file"]).read_text())
                    st.json(raw_json, expanded=False)
                except Exception as e:
                    st.warning(f"Could not load raw file: {e}")

            with col_std:
                st.subheader("Standardized record")
                st.json(row.dropna().to_dict(), expanded=True)

                rec_labs = lab_results[lab_results["record_id"] == chosen]
                if not rec_labs.empty:
                    st.markdown("**Lab results**")
                    st.dataframe(
                        rec_labs[["test_name_canonical", "result_value", "unit_canonical",
                                  "test_analytics", "flag_reason"]],
                        width='stretch', hide_index=True,
                    )

                rec_meds = medications[medications["record_id"] == chosen]
                if not rec_meds.empty:
                    st.markdown("**Medications**")
                    st.dataframe(
                        rec_meds[["medicine_original", "medicine_generic", "dose", "frequency"]],
                        width='stretch', hide_index=True,
                    )

# ---------------------------------------------------------------------------
# FR-5.4 Clinic-level Summary
# ---------------------------------------------------------------------------
with tab_clinic:
    records = load_table("records")
    lab_results = load_table("lab_results")
    dead_letters = load_table("dead_letters")

    if records.empty:
        st.info("No records yet-run the pipeline first.")
    else:
        summary_rows = []
        for clinic_id, grp in records.groupby("clinic_id"):
            total = len(grp)
            dup_count = grp["is_duplicate_of"].notna().sum()
            clinic_record_ids = set(grp["record_id"])
            clinic_labs = lab_results[lab_results["record_id"].isin(clinic_record_ids)]
            missing_field_rate = (
                grp[["patient_name", "diagnosis"]].isna().mean().mean() * 100
                if total else 0
            )
            unmapped_rate = (
                (clinic_labs["normalization_method"] == "unmapped").mean() * 100
                if not clinic_labs.empty else 0
            )
            summary_rows.append({
                "clinic_id": clinic_id,
                "records": total,
                "duplicate_rate_%": round(dup_count / total * 100, 1) if total else 0,
                "missing_field_rate_%": round(missing_field_rate, 1),
                "unmapped_test_name_rate_%": round(unmapped_rate, 1),
            })

        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(summary_df, width='stretch', hide_index=True)

        if not dead_letters.empty:
            st.caption(f"Plus {len(dead_letters)} file(s) that failed to parse entirely "
                       f"(dead-letter queue-not attributable to a clinic_id).")
