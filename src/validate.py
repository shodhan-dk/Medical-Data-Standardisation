"""
Validation & Analytics Flags module (FR-3). Consumes the already-
standardized (canonical unit) value, so it never has to know about raw
clinic formats — clean separation from standardize.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

with open(CONFIG_DIR / "reference_ranges.json", encoding="utf-8") as f:
    _RAW_RANGES = json.load(f)

REFERENCE_RANGES = {k: v for k, v in _RAW_RANGES.items() if not k.startswith("_")}
_DEFAULT_RANGE = _RAW_RANGES.get("_default", {})


def classify_result(
    canonical_test: str,
    value_canonical: float | None,
    is_numeric: bool,
    is_range_in_result_bug: bool,
) -> dict[str, Any]:
    """FR-3.1 Range Validation, FR-3.2 Outlier Detection, FR-3.3 Analytics
    Classification, FR-3.4 Incorrect Value Flagging — combined here since
    they all resolve to the single Test_Name_Analytics output field.

    Returns dict with test_analytics (one of Within Range / Above Range /
    Below Range / Outlier / Invalid / Unclassified) and flag_reason.
    """
    if is_range_in_result_bug:
        return {"test_analytics": "Invalid",
                "flag_reason": "result field contains a range, not a single value"}

    if not is_numeric or value_canonical is None:
        # legitimate qualitative result (POSITIVE/NEGATIVE/etc.) is not an
        # error — it's just not range-checkable. Distinguish that from a
        # test we expected to be numeric but got neither number nor a
        # recognized qualitative token by leaving flag_reason empty here;
        # the caller (pipeline) already filtered true garbage upstream.
        return {"test_analytics": "Not Applicable", "flag_reason": None}

    ranges = REFERENCE_RANGES.get(canonical_test, _DEFAULT_RANGE)
    low, high = ranges.get("low"), ranges.get("high")
    outlier_low, outlier_high = ranges.get("outlier_low"), ranges.get("outlier_high")

    if outlier_low is not None and value_canonical < outlier_low:
        return {"test_analytics": "Outlier",
                "flag_reason": f"{value_canonical} is below physiologically plausible floor {outlier_low}"}
    if outlier_high is not None and value_canonical > outlier_high:
        return {"test_analytics": "Outlier",
                "flag_reason": f"{value_canonical} is above physiologically plausible ceiling {outlier_high}"}

    if low is None or high is None:
        return {"test_analytics": "Unclassified",
                "flag_reason": f"no reference range configured for '{canonical_test}'"}

    if value_canonical < low:
        return {"test_analytics": "Below Range", "flag_reason": None}
    if value_canonical > high:
        return {"test_analytics": "Above Range", "flag_reason": None}
    return {"test_analytics": "Within Range", "flag_reason": None}
