"""Produce structured build metrics as JSON.

Complements the human-readable build_*_report.txt files. Every numeric
value that would show up in a build summary is captured here as a dict
so two builds can be compared programmatically via scripts/diff_metrics.py.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _value_counts(series):
    """Return value_counts as a plain dict with string keys (JSON-safe)."""
    if series is None or len(series) == 0:
        return {}
    vc = series.fillna("__null__").value_counts().to_dict()
    return {str(k): int(v) for k, v in vc.items()}


def collect_public(result, crosswalk=None):
    """Collect build metrics for the public coordinate pipeline."""
    metrics = {
        "pipeline": "public",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "row_count": int(len(result)),
        "with_coordinates": int(result["coord_source"].notna().sum()),
        "without_coordinates": int(result["coord_source"].isna().sum()),
        "coord_status": _value_counts(result.get("coord_status")),
        "coord_source": _value_counts(result.get("coord_source")),
        "coord_rejection_reason": _value_counts(result.get("coord_rejection_reason")),
        "location_source": _value_counts(result.get("location_source")),
        "psgc_validation": _value_counts(result.get("psgc_validation")),
        "enrollment_status": _value_counts(result.get("enrollment_status")),
        "coord_fallback_from": _value_counts(result.get("coord_fallback_from")),
        "school_id_length": _value_counts(result["school_id"].str.len().astype(str)),
    }

    if crosswalk is not None and len(crosswalk) > 0:
        metrics["crosswalk"] = {
            "rows": int(len(crosswalk)),
            "unique_canonical": int(crosswalk["canonical_id"].nunique()),
            "unique_historical": int(crosswalk["historical_id"].nunique()),
            "canonical_length": _value_counts(crosswalk["canonical_id"].str.len().astype(str)),
            "match_method": _value_counts(crosswalk["match_method"]),
        }

    return metrics


def collect_private(result):
    """Collect build metrics for the private coordinate pipeline."""
    return {
        "pipeline": "private",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "row_count": int(len(result)),
        "with_coordinates": int(result["coord_status"].isin(["valid", "fixed_swap"]).sum()),
        "coord_status": _value_counts(result.get("coord_status")),
        "coord_rejection_reason": _value_counts(result.get("coord_rejection_reason")),
        "psgc_validation": _value_counts(result.get("psgc_validation")),
        "enrollment_status": _value_counts(result.get("enrollment_status")),
        "gastpe": {
            "esc_participating": int(result["esc_participating"].sum()) if "esc_participating" in result.columns else 0,
            "shsvp_participating": int(result["shsvp_participating"].sum()) if "shsvp_participating" in result.columns else 0,
            "jdvp_participating": int(result["jdvp_participating"].sum()) if "jdvp_participating" in result.columns else 0,
        },
        "school_id_length": _value_counts(result["school_id"].str.len().astype(str)),
    }


def write(metrics, output_path):
    """Serialize metrics dict to JSON at output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"  Metrics written: {output_path}")
