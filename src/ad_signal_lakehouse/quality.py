"""Data quality checks and pipeline health reporting."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any


def build_pipeline_health_report(conn: sqlite3.Connection, generated_at: str) -> dict[str, Any]:
    counts = {
        "bronze_events": _scalar(conn, "SELECT COUNT(*) FROM bronze_events"),
        "silver_events": _scalar(conn, "SELECT COUNT(*) FROM silver_events"),
        "rejected_events": _scalar(conn, "SELECT COUNT(*) FROM rejected_events"),
        "duplicate_events": _scalar(conn, "SELECT COUNT(*) FROM silver_events WHERE is_duplicate = 1"),
        "late_events": _scalar(conn, "SELECT COUNT(*) FROM silver_events WHERE is_late = 1"),
        "negative_spend_in_silver": _scalar(
            conn,
            "SELECT COUNT(*) FROM silver_events WHERE cost_usd < 0",
        ),
        "gold_campaign_rows": _scalar(conn, "SELECT COUNT(*) FROM gold_campaign_daily"),
        "gold_channel_rows": _scalar(conn, "SELECT COUNT(*) FROM gold_channel_daily"),
        "campaign_anomaly_rows": _scalar(
            conn,
            "SELECT COUNT(*) FROM gold_campaign_daily WHERE anomaly_flags <> 'none'",
        ),
    }

    rejection_reasons = {
        row["reason"]: row["count"]
        for row in conn.execute(
            """
            SELECT reason, COUNT(*) AS count
            FROM rejected_events
            GROUP BY reason
            ORDER BY count DESC, reason
            """
        )
    }

    gates = [
        _gate("bronze_loaded", counts["bronze_events"] > 0, "Bronze JSONL contains at least one row."),
        _gate("silver_loaded", counts["silver_events"] > 0, "At least one validated row reached silver."),
        _gate(
            "reject_rate_under_5_percent",
            _rate(counts["rejected_events"], counts["bronze_events"]) <= 0.05,
            "Schema and guardrail rejects stay under 5 percent.",
        ),
        _gate(
            "duplicate_rate_under_5_percent",
            _rate(counts["duplicate_events"], counts["silver_events"]) <= 0.05,
            "Duplicate event ids stay under 5 percent of silver rows.",
        ),
        _gate(
            "negative_spend_blocked",
            counts["negative_spend_in_silver"] == 0,
            "Negative spend is rejected before silver/gold.",
        ),
        _gate("gold_built", counts["gold_campaign_rows"] > 0, "Gold KPI tables contain aggregate rows."),
    ]

    return {
        "status": "pass" if all(gate["passed"] for gate in gates) else "fail",
        "generated_at": generated_at,
        "counts": counts,
        "rates": {
            "reject_rate": round(_rate(counts["rejected_events"], counts["bronze_events"]), 4),
            "duplicate_rate": round(_rate(counts["duplicate_events"], counts["silver_events"]), 4),
            "late_event_rate": round(_rate(counts["late_events"], counts["silver_events"]), 4),
        },
        "rejection_reasons": rejection_reasons,
        "quality_gates": gates,
    }


def write_json_report(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _scalar(conn: sqlite3.Connection, query: str) -> int:
    value = conn.execute(query).fetchone()[0]
    return int(value or 0)


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _gate(name: str, passed: bool, description: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "description": description}
