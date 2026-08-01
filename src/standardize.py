"""
Standardization module (FR-2). All lookups are loaded from /config at
import time — adding a new test-name variant, unit, or medicine is a
config edit, not a code change (NFR-2.1).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return json.load(f)


TEST_NAME_MAP = {k: v for k, v in _load("test_name_map.json").items() if not k.startswith("_")}
UNIT_MAP = {k: v for k, v in _load("unit_map.json").items() if not k.startswith("_")}
MEDICINE_MAP = {k: v for k, v in _load("medicine_map.json").items() if not k.startswith("_")}

_CANONICAL_TEST_NAMES = sorted(set(TEST_NAME_MAP.values()))
_FUZZY_MATCH_THRESHOLD = 80  # 0-100; below this, a test name is left "unmapped" for manual review


# ---------------------------------------------------------------------------
# FR-2.1 Test Name Normalisation
# ---------------------------------------------------------------------------

def normalize_test_name(raw_name: str) -> tuple[str, str, float]:
    """Returns (canonical_name, method, confidence).

    method is one of 'exact', 'fuzzy', 'unmapped'. Exact match is a
    case-insensitive dictionary lookup; fuzzy match handles OCR-truncated
    or misspelled names (e.g. 'aemoglobin' for 'Haemoglobin') using
    token-set similarity against both the dictionary keys and the
    canonical names themselves, so a truncation still resolves as long
    as the remaining characters are distinctive enough.
    """
    if not raw_name or not raw_name.strip():
        return "", "unmapped", 0.0

    key = raw_name.strip().upper()

    if key in TEST_NAME_MAP:
        return TEST_NAME_MAP[key], "exact", 100.0

    # fuzzy against dictionary keys (captures known misspellings/truncations)
    candidates = list(TEST_NAME_MAP.keys()) + _CANONICAL_TEST_NAMES
    match = process.extractOne(key, candidates, scorer=fuzz.token_set_ratio)
    if match and match[1] >= _FUZZY_MATCH_THRESHOLD:
        matched_key = match[0]
        canonical = TEST_NAME_MAP.get(matched_key, matched_key)
        return canonical, "fuzzy", float(match[1])

    # No confident match — surface the original, flagged for a human /
    # config maintainer to add a mapping (NFR-4.1 tracks this coverage %).
    return raw_name.strip(), "unmapped", float(match[1]) if match else 0.0


# ---------------------------------------------------------------------------
# FR-2.3 Numeric Conversion
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")

_TEXT_RESULT_VALUES = {"positive", "negative", "reactive", "non-reactive",
                        "detected", "not detected", "nil", "trace", "n/a", "na"}


def extract_numeric_and_unit(result_raw: str, unit_hint: str | None = None) -> dict[str, Any]:
    """FR-2.3: pulls a numeric value out of messy result strings.

    Handles:
      - pure numeric: "9700" -> 9700.0
      - numeric + embedded unit: "120000 cells/cu.mm" -> 120000.0, unit="cells/cu.mm"
      - a *range* mistakenly placed in the result field (data quality bug
        seen in file2, e.g. result_text == "1.5-4.5"): treated as
        non-numeric/invalid rather than silently averaging or guessing
      - pure text results (POSITIVE/NEGATIVE/qualitative): value stays
        None, result_text_original is preserved for downstream review
    """
    out = {"result_value": None, "unit_extracted": None, "is_numeric": False,
           "is_range_in_result_bug": False}

    if result_raw is None:
        return out
    text = str(result_raw).strip()
    if not text:
        return out

    lowered = text.lower()
    if lowered in _TEXT_RESULT_VALUES:
        return out  # legitimately qualitative — not an error

    # bug pattern: "1.5-4.5" landed in the result field (should be a range)
    if re.fullmatch(r"-?\d+(?:\.\d+)?\s*-\s*-?\d+(?:\.\d+)?", text):
        out["is_range_in_result_bug"] = True
        return out

    numbers = _NUMERIC_RE.findall(text)
    if not numbers:
        return out  # non-numeric qualitative text, e.g. "POSITIVE"

    out["result_value"] = float(numbers[0])
    out["is_numeric"] = True

    # anything after the number, stripped of separators, is treated as an
    # embedded unit if the caller didn't already have one from a separate field
    remainder = text[text.find(numbers[0]) + len(numbers[0]):].strip(" ,")
    if remainder and not unit_hint:
        out["unit_extracted"] = remainder

    return out


# ---------------------------------------------------------------------------
# FR-2.4 Unit Harmonisation
# ---------------------------------------------------------------------------

def harmonize_unit(canonical_test: str, value: float | None, unit_raw: str | None) -> dict[str, Any]:
    """Converts value into the canonical unit for this test, if we have a
    conversion factor configured. Unrecognized units are passed through
    unconverted with the original preserved — better a visible flag than
    a silent wrong conversion (FR-3.4 will catch this downstream)."""
    cfg = UNIT_MAP.get(canonical_test, UNIT_MAP.get("_default", {}))
    canonical_unit = cfg.get("canonical_unit")
    aliases = cfg.get("aliases", {})

    if value is None:
        return {"unit_canonical": canonical_unit, "value_canonical": None}

    if not unit_raw:
        return {"unit_canonical": canonical_unit, "value_canonical": value}

    factor = aliases.get(unit_raw.strip().lower())
    if factor is not None:
        return {"unit_canonical": canonical_unit, "value_canonical": value * factor}

    # unrecognized unit for this test — pass through, don't guess
    return {"unit_canonical": unit_raw, "value_canonical": value}


# ---------------------------------------------------------------------------
# FR-2.5 Demographic Normalisation (age / gender / dates)
# ---------------------------------------------------------------------------

_AGE_PATTERN = re.compile(
    r"(?:(?P<y>\d+)\s*Y)?\s*(?:(?P<m>\d+)\s*M)?\s*(?:(?P<d>\d+)\s*D)?", re.IGNORECASE
)


def normalize_age(age_raw: str | None) -> float | None:
    """'33Y11M265D' -> 33.75 (years, decimal). A plain '33' or '33 years'
    is treated as whole years. Returns None if unparseable (e.g. redacted)."""
    if not age_raw:
        return None
    text = str(age_raw).strip()
    if text.upper() in {"[AGE REDACTED]", "N/A", "NA", ""}:
        return None

    m = _AGE_PATTERN.search(text)
    if m and (m.group("y") or m.group("m") or m.group("d")):
        years = int(m.group("y") or 0)
        months = int(m.group("m") or 0)
        days = int(m.group("d") or 0)
        return round(years + months / 12 + days / 365.25, 2)

    plain = re.search(r"\d+", text)
    return float(plain.group()) if plain else None


_GENDER_MAP = {
    "M": "Male", "MALE": "Male",
    "F": "Female", "FEMALE": "Female",
    "O": "Other", "OTHER": "Other",
}


def normalize_gender(gender_raw: str | None) -> str | None:
    if not gender_raw:
        return None
    key = str(gender_raw).strip().upper()
    if key in {"[GENDER REDACTED]", "N/A", "NA", ""}:
        return None
    return _GENDER_MAP.get(key, gender_raw.strip().title())


_DATE_FORMATS = ["%d-%m-%Y", "%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]


def normalize_date(date_raw: str | None) -> str | None:
    """Multiple incoming formats -> ISO 8601 (YYYY-MM-DD)."""
    if not date_raw:
        return None
    text = str(date_raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None  # unparseable — left null, flagged via processing_status upstream


# ---------------------------------------------------------------------------
# FR-2.6 Medicine Name Mapping
# ---------------------------------------------------------------------------

_DOSAGE_STRIP_RE = re.compile(r"\b\d+(\.\d+)?\s*(MG|ML|GM|G|MCG)\b", re.IGNORECASE)
_PREFIX_STRIP_RE = re.compile(r"^(TAB\.?|CAP\.?|INJ\.?|SYP\.?|POWDER)\s+", re.IGNORECASE)


def normalize_medicine(medicine_raw: str | None) -> tuple[str | None, str]:
    """Returns (generic_name_or_None, method). Strips dosage form prefix
    (Tab./Cap./Inj./Syp.) and strength suffix (500 MG) before lookup, so
    'TAB CEFTUM 500 MG' matches the 'CEFTUM' config entry."""
    if not medicine_raw:
        return None, "unmapped"
    text = medicine_raw.strip()
    stripped = _PREFIX_STRIP_RE.sub("", text)
    stripped = _DOSAGE_STRIP_RE.sub("", stripped).strip()
    key = stripped.upper()

    if key in MEDICINE_MAP:
        return MEDICINE_MAP[key], "exact"

    match = process.extractOne(key, list(MEDICINE_MAP.keys()), scorer=fuzz.token_set_ratio)
    if match and match[1] >= 85:
        return MEDICINE_MAP[match[0]], "fuzzy"

    return None, "unmapped"
