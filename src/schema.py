"""
Canonical schema for the Veritas Claims standardization pipeline.

Design note (see /docs/assumptions.md, 'Data Assumptions'):
The provided Ourput-table-ideal-schema.csv is a UNION of every field name
seen across the 5 sample files (it contains near-duplicates like
`medicine` / `medication_medicine` / `dischargeMedications_medicine`).
That's a useful field inventory but not a good target table shape — a
78-column-wide, mostly-null table doesn't scale as new clinics/report
types are onboarded. Instead we normalize into three related tables:

  records        - one row per source document (visit-level fields:
                   patient/demographic, admission/discharge, diagnosis,
                   lineage/audit columns)
  lab_results     - one row per (record, test) — long format, so a new
                   test doesn't require a new column
  medications     - one row per (record, medication)

This is a config-driven, schema-on-read-friendly shape: onboarding a new
clinic's field names only touches /config, never these table defs.
"""

RECORDS_COLUMNS = [
    "record_id",            # PK - stable hash, see ingestion.compute_record_id
    "document_id",
    "trace_id",
    "correlation_id",
    "source_system",
    "claim_no",
    "nt_code",
    "consumer_client_id",
    "clinic_id",
    "record_type",          # discharge_summary | lab_report
    "patient_name",
    "age_raw",
    "age_years",
    "gender_raw",
    "gender_canonical",
    "uhid",
    "hospital_name",
    "hospital_address",
    "doctor_name",
    "ward",
    "admission_date_raw",
    "admission_date_iso",
    "discharge_date_raw",
    "discharge_date_iso",
    "report_date_raw",
    "report_date_iso",
    "diagnosis",
    "brief_history",
    "general_examinations",
    "recommendations",
    "post_discharge_advice",
    "course_during_hospitalisation",
    "source_file",
    "ingested_at",
    "processed_at",
    "is_duplicate_of",       # record_id of the earlier copy, if this is a dup
    "processing_status",     # success | error
    "error_reason",
]

LAB_RESULTS_COLUMNS = [
    "result_id",             # PK
    "record_id",             # FK -> records.record_id
    "page_no",
    "test_name_original",
    "test_name_canonical",
    "normalization_method",  # exact | fuzzy | unmapped
    "normalization_confidence",
    "result_text_original",
    "result_value",          # numeric, if extractable
    "unit_original",
    "unit_canonical",
    "range_text_original",
    "range_low",
    "range_high",
    "test_analytics",        # Within Range | Above Range | Below Range | Outlier | Invalid
    "flag_reason",
]

MEDICATIONS_COLUMNS = [
    "medication_id",         # PK
    "record_id",             # FK -> records.record_id
    "medicine_original",
    "medicine_generic",
    "dose",
    "frequency",
    "medicine_type",
]
