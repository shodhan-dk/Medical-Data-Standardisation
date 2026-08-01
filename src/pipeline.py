"""
End-to-end pipeline orchestrator. This is what /src/main.py and the UI's
"Run Pipeline" button both call.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from . import db, standardize, validate
from .ingestion import RawEnvelope, compute_patient_dedup_key, compute_record_id, run_ingestion


def _extract_discharge_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "patient_name": data.get("patientName"),
        "age_raw": data.get("age"),
        "gender_raw": data.get("gender"),
        "hospital_name": data.get("hospitalName"),
        "hospital_address": data.get("hospitalAddress"),
        "doctor_name": data.get("doctorName"),
        "ward": data.get("ward"),
        "admission_date_raw": data.get("admissionDate"),
        "discharge_date_raw": data.get("dischargeDate"),
        "diagnosis": data.get("diagnosis"),
        "brief_history": data.get("briefHistory"),
        "general_examinations": data.get("generalExaminations"),
        "recommendations": data.get("recommendations"),
        "post_discharge_advice": data.get("postDischargeAdvice"),
        "course_during_hospitalisation": json_join(data.get("courseDuringHospitalisation")),
    }


def _extract_lab_fields(data: dict[str, Any]) -> dict[str, Any]:
    basic = data.get("basic_info") or {}
    return {
        "patient_name": basic.get("patient_name"),
        "age_raw": basic.get("age"),
        "gender_raw": basic.get("gender"),
        "hospital_name": basic.get("lab_or_hospital_name"),
        "uhid": basic.get("uhid"),
        "report_date_raw": basic.get("reports_date"),
    }


def json_join(value) -> str | None:
    if not value:
        return None
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v)
    return str(value)


def process_envelope(envelope: RawEnvelope, conn, seen_dedup_keys: dict[str, str], stats: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()

    for idx, detail in enumerate(envelope.response_details):
        classifier = detail.get("classifier", "unknown")
        data = detail.get("data") or {}
        record_id = compute_record_id(envelope, idx, classifier)

        if classifier == "discharge_summary":
            fields = _extract_discharge_fields(data)
        elif classifier == "lab_report":
            fields = _extract_lab_fields(data)
        else:
            fields = {}

        dedup_key = compute_patient_dedup_key(classifier, {
            "patient_name": fields.get("patient_name"),
            "admission_date": fields.get("admission_date_raw") or fields.get("report_date_raw"),
            "diagnosis": fields.get("diagnosis"),
            "hospital_name": fields.get("hospital_name"),
        })
        is_dup = dedup_key in seen_dedup_keys
        if is_dup:
            stats["duplicates_suppressed"] += 1
        else:
            seen_dedup_keys[dedup_key] = record_id

        record_row = {
            "record_id": record_id,
            "document_id": envelope.document_id,
            "trace_id": envelope.trace_id,
            "correlation_id": envelope.correlation_id,
            "source_system": envelope.meta.get("source_system"),
            "claim_no": envelope.meta.get("claim_no"),
            "nt_code": envelope.meta.get("nt_code"),
            "consumer_client_id": envelope.meta.get("ConsumerClientId"),
            "clinic_id": envelope.clinic_id,
            "record_type": classifier,
            "patient_name": fields.get("patient_name"),
            "age_raw": fields.get("age_raw"),
            "age_years": standardize.normalize_age(fields.get("age_raw")),
            "gender_raw": fields.get("gender_raw"),
            "gender_canonical": standardize.normalize_gender(fields.get("gender_raw")),
            "uhid": fields.get("uhid"),
            "hospital_name": fields.get("hospital_name"),
            "hospital_address": fields.get("hospital_address"),
            "doctor_name": fields.get("doctor_name"),
            "ward": fields.get("ward"),
            "admission_date_raw": fields.get("admission_date_raw"),
            "admission_date_iso": standardize.normalize_date(fields.get("admission_date_raw")),
            "discharge_date_raw": fields.get("discharge_date_raw"),
            "discharge_date_iso": standardize.normalize_date(fields.get("discharge_date_raw")),
            "report_date_raw": fields.get("report_date_raw"),
            "report_date_iso": standardize.normalize_date(fields.get("report_date_raw")),
            "diagnosis": fields.get("diagnosis"),
            "brief_history": fields.get("brief_history"),
            "general_examinations": fields.get("general_examinations"),
            "recommendations": fields.get("recommendations"),
            "post_discharge_advice": fields.get("post_discharge_advice"),
            "course_during_hospitalisation": fields.get("course_during_hospitalisation"),
            "source_file": envelope.source_file,
            "ingested_at": envelope.ingested_at,
            "processed_at": now,
            "is_duplicate_of": seen_dedup_keys[dedup_key] if is_dup else None,
            "processing_status": "success",
            "error_reason": None,
        }
        db.upsert_record(conn, record_row)
        stats["records_total"] += 1

        # -- lab results (long format) --
        for r_idx, r in enumerate(data.get("report_details") or []):
            raw_name = r.get("test_name", "")
            canonical, method, confidence = standardize.normalize_test_name(raw_name)

            numeric_info = standardize.extract_numeric_and_unit(r.get("result"), r.get("unit"))
            harmon = standardize.harmonize_unit(canonical, numeric_info["result_value"],
                                                 r.get("unit") or numeric_info["unit_extracted"])
            analytics = validate.classify_result(
                canonical, harmon["value_canonical"], numeric_info["is_numeric"],
                numeric_info["is_range_in_result_bug"],
            )

            range_low, range_high = _parse_range(r.get("range"))

            result_row = {
                "result_id": f"{record_id}:lr:{r_idx}",
                "record_id": record_id,
                "page_no": r.get("page_no"),
                "test_name_original": raw_name,
                "test_name_canonical": canonical,
                "normalization_method": method,
                "normalization_confidence": confidence,
                "result_text_original": r.get("result"),
                "result_value": harmon["value_canonical"],
                "unit_original": r.get("unit"),
                "unit_canonical": harmon["unit_canonical"],
                "range_text_original": r.get("range"),
                "range_low": range_low,
                "range_high": range_high,
                "test_analytics": analytics["test_analytics"],
                "flag_reason": analytics["flag_reason"],
            }
            db.upsert_lab_result(conn, result_row)
            if analytics["test_analytics"] in {"Outlier", "Invalid", "Above Range", "Below Range"}:
                stats["records_flagged"] += 1

        # -- medications --
        for m_idx, m in enumerate(data.get("dischargeMedications") or []):
            generic, method = standardize.normalize_medicine(m.get("medicine"))
            med_row = {
                "medication_id": f"{record_id}:med:{m_idx}",
                "record_id": record_id,
                "medicine_original": m.get("medicine"),
                "medicine_generic": generic,
                "dose": m.get("dose"),
                "frequency": m.get("frequency"),
                "medicine_type": m.get("type"),
            }
            db.upsert_medication(conn, med_row)


def _parse_range(range_text: str | None) -> tuple[float | None, float | None]:
    if not range_text:
        return None, None
    import re
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$", str(range_text))
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def run_pipeline(input_dir: str, db_path: str | None = None) -> dict:
    """FR-4.1 entry point. Returns a summary stats dict (also written to
    pipeline_runs for the UI dashboard, FR-5.1)."""
    conn = db.get_connection(db_path or db.DB_PATH)
    db.init_db(conn)

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    stats = {"records_total": 0, "records_flagged": 0, "duplicates_suppressed": 0}

    envelopes, dead_letters = run_ingestion(input_dir)

    seen_dedup_keys: dict[str, str] = {}
    for envelope in envelopes:
        process_envelope(envelope, conn, seen_dedup_keys, stats)

    for dl in dead_letters:
        db.insert_dead_letter(conn, dl)

    finished_at = datetime.now(timezone.utc).isoformat()
    run_stats = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "files_total": len(envelopes) + len(dead_letters),
        "files_success": len(envelopes),
        "files_failed": len(dead_letters),
        **stats,
    }
    db.record_run(conn, run_stats)
    conn.commit()
    conn.close()
    return run_stats
