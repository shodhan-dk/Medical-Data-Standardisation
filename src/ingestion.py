"""
Ingestion module (FR-1).

Simulates a GCS bucket with a local folder (per the assignment scope note
in 3.2). In production, `discover_files` would be replaced by a GCS event
trigger (Pub/Sub notification on object finalize) or a Cloud Scheduler
sweep — see /docs/architecture.md — but the interface below
(iterate over "landed files", yield parsed+validated envelopes) stays
the same either way, which is the point: the standardization/validation
modules never know or care where the file came from.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger("veritas.ingestion")


@dataclass
class RawEnvelope:
    """One clinic JSON file, parsed but not yet standardized."""
    source_file: str
    trace_id: str | None
    correlation_id: str | None
    document_id: str | None
    meta: dict[str, str]
    response_details: list[dict[str, Any]]
    ingested_at: str
    clinic_id: str


@dataclass
class DeadLetter:
    source_file: str
    reason: str
    raised_at: str
    detail: str = ""


def discover_files(input_dir: str) -> list[Path]:
    """FR-1.1 (Multi-source ingestion): list JSON files ready to process.

    In production this becomes a GCS listing filtered by a processed-files
    ledger (or a Pub/Sub push per new object) instead of a directory walk —
    same contract, different trigger.
    """
    p = Path(input_dir)
    return sorted(p.glob("*.json"))


def infer_clinic_id(meta: dict[str, str], source_file: str) -> str:
    """FR-1.3 (Schema flexibility): clinic identity drives which config
    mappings apply. We prefer explicit metadata; fall back to source_system,
    then to an 'unknown' bucket that still gets processed (best-effort
    default mappings) rather than dropped — see architecture doc, error
    handling section, for the reprocessing story once a real clinic_id is
    known.
    """
    return meta.get("source_system") or meta.get("nt_code") or "UNKNOWN_CLINIC"


def parse_file(path: Path) -> RawEnvelope | DeadLetter:
    """Parse + structurally validate one file. Never raises — malformed
    input becomes a DeadLetter record instead of crashing the batch
    (NFR-3.1 Fault Tolerance)."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        return DeadLetter(str(path), "read_error", now, str(e))

    try:
        doc = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return DeadLetter(str(path), "invalid_json", now, str(e))

    data = doc.get("data")
    if not isinstance(data, dict):
        return DeadLetter(str(path), "missing_data_block", now,
                           "top-level 'data' object not found")

    response_details = data.get("responseDetails")
    if not isinstance(response_details, list) or not response_details:
        return DeadLetter(str(path), "missing_response_details", now,
                           "'data.responseDetails' missing or empty")

    meta_list = data.get("metaDetails") or []
    meta = {m.get("key"): m.get("value") for m in meta_list if isinstance(m, dict)}

    return RawEnvelope(
        source_file=str(path),
        trace_id=doc.get("traceId"),
        correlation_id=data.get("correlationId"),
        document_id=data.get("documentId"),
        meta=meta,
        response_details=response_details,
        ingested_at=now,
        clinic_id=infer_clinic_id(meta, str(path)),
    )


def compute_record_id(envelope: RawEnvelope, detail_index: int, classifier: str) -> str:
    """Stable content hash used both as the DB primary key and as the
    dedup key (FR-1.2, NFR-3.2 Idempotency). Keyed on document_id +
    classifier + position rather than a random UUID, so re-ingesting the
    *same* source file always produces the *same* record_id -> upsert,
    not insert -> no duplicate rows on re-run.
    """
    basis = f"{envelope.document_id}|{envelope.correlation_id}|{classifier}|{detail_index}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def compute_patient_dedup_key(record_type: str, patient_fields: dict[str, Any]) -> str:
    """FR-1.2 Duplicate Detection (business-level, not just re-ingest):
    the same patient's discharge summary submitted twice from different
    systems. We hash on fields that should be stable for one true visit —
    NOT patient_name alone (too many collisions / PII-heavy), but
    admission+discharge date + diagnosis + hospital, which is
    configurable (see config/dedup_keys.json) so a clinic with different
    stable identifiers doesn't require a code change.
    """
    basis = "|".join(str(patient_fields.get(k, "")).strip().lower()
                      for k in sorted(patient_fields.keys()))
    return hashlib.sha256(f"{record_type}|{basis}".encode("utf-8")).hexdigest()[:24]


def run_ingestion(input_dir: str) -> tuple[list[RawEnvelope], list[DeadLetter]]:
    """Top-level entry point for FR-1. Returns (good envelopes, dead letters)."""
    good: list[RawEnvelope] = []
    bad: list[DeadLetter] = []
    for path in discover_files(input_dir):
        result = parse_file(path)
        if isinstance(result, DeadLetter):
            logger.error("dead_letter file=%s reason=%s detail=%s",
                         result.source_file, result.reason, result.detail)
            bad.append(result)
        else:
            good.append(result)
    return good, bad
