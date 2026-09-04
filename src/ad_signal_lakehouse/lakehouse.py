"""Bronze, silver, and gold medallion pipeline implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from .dashboard import render_dashboard
from .generator import generate_events
from .models import CHANNELS, EVENT_TYPES, REQUIRED_FIELDS
from .quality import build_pipeline_health_report, write_json_report


LATE_EVENT_HOURS = 24


@dataclass(frozen=True)
class DemoResult:
    output_dir: Path
    bronze_file: Path
    database_path: Path
    health_report_path: Path
    dashboard_path: Path
    status: str
    counts: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_demo(output: str | Path, events: int, seed: int = 42) -> DemoResult:
    output_dir = Path(output)
    bronze_dir = output_dir / "bronze"
    report_dir = output_dir / "reports"
    dashboard_dir = output_dir / "dashboard"
    for path in (bronze_dir, report_dir, dashboard_dir):
        path.mkdir(parents=True, exist_ok=True)

    generated_events = generate_events(events, seed=seed)
    bronze_file = write_bronze_jsonl(
        generated_events,
        _next_bronze_path(bronze_dir, seed=seed, event_count=events),
    )

    database_path = output_dir / "lakehouse.db"
    if database_path.exists():
        database_path.unlink()

    with connect(database_path) as conn:
        create_schema(conn)
        load_bronze(conn, bronze_file)
        build_silver(conn)
        build_gold(conn)
        health = build_pipeline_health_report(conn, generated_at=utc_now_iso())
        health_report_path = write_json_report(health, report_dir / "pipeline_health.json")
        dashboard_path = render_dashboard(
            conn,
            health,
            dashboard_dir / "index.html",
            database_path=database_path,
            bronze_file=bronze_file,
        )

    return DemoResult(
        output_dir=output_dir,
        bronze_file=bronze_file,
        database_path=database_path,
        health_report_path=health_report_path,
        dashboard_path=dashboard_path,
        status=health["status"],
        counts=health["counts"],
    )


def write_bronze_jsonl(events: list[dict[str, Any]], path: Path) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    return path


def _next_bronze_path(bronze_dir: Path, seed: int, event_count: int) -> Path:
    base = bronze_dir / f"ad_events_seed{seed}_n{event_count}.jsonl"
    if not base.exists():
        return base

    suffix = 2
    while True:
        candidate = bronze_dir / f"ad_events_seed{seed}_n{event_count}_{suffix:03d}.jsonl"
        if not candidate.exists():
            return candidate
        suffix += 1


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE bronze_events (
            bronze_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            loaded_at TEXT NOT NULL
        );

        CREATE TABLE silver_events (
            silver_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bronze_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            event_ts TEXT NOT NULL,
            ingest_ts TEXT NOT NULL,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            device TEXT,
            geo TEXT,
            placement TEXT,
            cost_usd REAL NOT NULL,
            revenue_usd REAL NOT NULL,
            is_late INTEGER NOT NULL,
            is_duplicate INTEGER NOT NULL,
            quality_status TEXT NOT NULL,
            FOREIGN KEY (bronze_id) REFERENCES bronze_events(bronze_id)
        );

        CREATE TABLE rejected_events (
            rejected_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bronze_id INTEGER NOT NULL,
            event_id TEXT,
            reason TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            rejected_at TEXT NOT NULL,
            FOREIGN KEY (bronze_id) REFERENCES bronze_events(bronze_id)
        );

        CREATE TABLE gold_campaign_daily (
            event_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT NOT NULL,
            spend REAL NOT NULL,
            impressions INTEGER NOT NULL,
            clicks INTEGER NOT NULL,
            conversions INTEGER NOT NULL,
            revenue REAL NOT NULL,
            ctr REAL NOT NULL,
            cpc REAL NOT NULL,
            cpa REAL NOT NULL,
            roas REAL NOT NULL,
            anomaly_flags TEXT NOT NULL,
            PRIMARY KEY (event_date, campaign_id)
        );

        CREATE TABLE gold_channel_daily (
            event_date TEXT NOT NULL,
            channel TEXT NOT NULL,
            spend REAL NOT NULL,
            impressions INTEGER NOT NULL,
            clicks INTEGER NOT NULL,
            conversions INTEGER NOT NULL,
            revenue REAL NOT NULL,
            ctr REAL NOT NULL,
            cpc REAL NOT NULL,
            cpa REAL NOT NULL,
            roas REAL NOT NULL,
            anomaly_flags TEXT NOT NULL,
            PRIMARY KEY (event_date, channel)
        );
        """
    )
    conn.commit()


def load_bronze(conn: sqlite3.Connection, bronze_file: Path) -> int:
    loaded_at = utc_now_iso()
    rows = []
    with bronze_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                rows.append((str(bronze_file), line_number, line.strip(), loaded_at))

    conn.executemany(
        """
        INSERT INTO bronze_events (source_file, line_number, payload_json, loaded_at)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def build_silver(conn: sqlite3.Connection) -> dict[str, int]:
    seen_event_ids: set[str] = set()
    accepted = 0
    rejected = 0
    duplicates = 0

    bronze_rows = conn.execute(
        "SELECT bronze_id, payload_json FROM bronze_events ORDER BY bronze_id"
    )

    for row in bronze_rows:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError as exc:
            _insert_rejection(conn, row["bronze_id"], None, f"invalid_json:{exc.msg}", row["payload_json"])
            rejected += 1
            continue

        normalized, errors = validate_event(payload)
        if errors:
            _insert_rejection(
                conn,
                row["bronze_id"],
                str(payload.get("event_id", "")),
                ",".join(errors),
                row["payload_json"],
            )
            rejected += 1
            continue

        is_duplicate = normalized["event_id"] in seen_event_ids
        if is_duplicate:
            duplicates += 1
        else:
            seen_event_ids.add(normalized["event_id"])

        conn.execute(
            """
            INSERT INTO silver_events (
                bronze_id, event_id, event_ts, ingest_ts, event_date, event_type,
                channel, campaign_id, campaign_name, user_id, device, geo, placement,
                cost_usd, revenue_usd, is_late, is_duplicate, quality_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["bronze_id"],
                normalized["event_id"],
                normalized["event_ts"],
                normalized["ingest_ts"],
                normalized["event_date"],
                normalized["event_type"],
                normalized["channel"],
                normalized["campaign_id"],
                normalized["campaign_name"],
                normalized["user_id"],
                normalized.get("device"),
                normalized.get("geo"),
                normalized.get("placement"),
                normalized["cost_usd"],
                normalized["revenue_usd"],
                normalized["is_late"],
                int(is_duplicate),
                "accepted",
            ),
        )
        accepted += 1

    conn.commit()
    return {"accepted": accepted, "rejected": rejected, "duplicates": duplicates}


def validate_event(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing_{field}")

    if errors:
        return {}, errors

    event_type = str(payload["event_type"])
    channel = str(payload["channel"])
    cost_usd = _coerce_float(payload.get("cost_usd"), "cost_usd", errors)
    revenue_usd = _coerce_float(payload.get("revenue_usd"), "revenue_usd", errors)
    event_ts = _parse_iso(payload.get("event_ts"), "event_ts", errors)
    ingest_ts = _parse_iso(payload.get("ingest_ts"), "ingest_ts", errors)

    if not str(payload["event_id"]).strip():
        errors.append("blank_event_id")
    if event_type not in EVENT_TYPES:
        errors.append("unknown_event_type")
    if channel not in CHANNELS:
        errors.append("unknown_channel")
    if cost_usd is not None and cost_usd < 0:
        errors.append("negative_spend")
    if revenue_usd is not None and revenue_usd < 0:
        errors.append("negative_revenue")

    if errors:
        return {}, errors

    assert cost_usd is not None
    assert revenue_usd is not None
    assert event_ts is not None
    assert ingest_ts is not None

    is_late = int((ingest_ts - event_ts).total_seconds() > LATE_EVENT_HOURS * 3600)
    return (
        {
            "event_id": str(payload["event_id"]),
            "event_ts": _format_iso(event_ts),
            "ingest_ts": _format_iso(ingest_ts),
            "event_date": event_ts.date().isoformat(),
            "event_type": event_type,
            "channel": channel,
            "campaign_id": str(payload["campaign_id"]),
            "campaign_name": str(payload["campaign_name"]),
            "user_id": str(payload["user_id"]),
            "device": payload.get("device"),
            "geo": payload.get("geo"),
            "placement": payload.get("placement"),
            "cost_usd": round(cost_usd, 2),
            "revenue_usd": round(revenue_usd, 2),
            "is_late": is_late,
        },
        [],
    )


def build_gold(conn: sqlite3.Connection) -> None:
    base_rows = conn.execute(
        """
        SELECT
            event_date,
            channel,
            campaign_id,
            campaign_name,
            SUM(CASE WHEN event_type = 'spend' THEN cost_usd ELSE 0 END) AS spend,
            SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) AS impressions,
            SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS clicks,
            SUM(CASE WHEN event_type = 'conversion' THEN 1 ELSE 0 END) AS conversions,
            SUM(revenue_usd) AS revenue
        FROM silver_events
        WHERE quality_status = 'accepted' AND is_duplicate = 0
        GROUP BY event_date, channel, campaign_id, campaign_name
        ORDER BY event_date, channel, campaign_id
        """
    ).fetchall()

    campaign_rows = []
    for row in base_rows:
        metrics = _compute_metrics(
            spend=row["spend"] or 0.0,
            impressions=row["impressions"] or 0,
            clicks=row["clicks"] or 0,
            conversions=row["conversions"] or 0,
            revenue=row["revenue"] or 0.0,
        )
        campaign_rows.append(
            (
                row["event_date"],
                row["channel"],
                row["campaign_id"],
                row["campaign_name"],
                metrics["spend"],
                metrics["impressions"],
                metrics["clicks"],
                metrics["conversions"],
                metrics["revenue"],
                metrics["ctr"],
                metrics["cpc"],
                metrics["cpa"],
                metrics["roas"],
                ",".join(_anomaly_flags(metrics)) or "none",
            )
        )

    conn.executemany(
        """
        INSERT INTO gold_campaign_daily (
            event_date, channel, campaign_id, campaign_name, spend, impressions,
            clicks, conversions, revenue, ctr, cpc, cpa, roas, anomaly_flags
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        campaign_rows,
    )

    channel_rows = conn.execute(
        """
        SELECT
            event_date,
            channel,
            SUM(spend) AS spend,
            SUM(impressions) AS impressions,
            SUM(clicks) AS clicks,
            SUM(conversions) AS conversions,
            SUM(revenue) AS revenue
        FROM gold_campaign_daily
        GROUP BY event_date, channel
        ORDER BY event_date, channel
        """
    ).fetchall()

    conn.executemany(
        """
        INSERT INTO gold_channel_daily (
            event_date, channel, spend, impressions, clicks, conversions, revenue,
            ctr, cpc, cpa, roas, anomaly_flags
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["event_date"],
                row["channel"],
                metrics["spend"],
                metrics["impressions"],
                metrics["clicks"],
                metrics["conversions"],
                metrics["revenue"],
                metrics["ctr"],
                metrics["cpc"],
                metrics["cpa"],
                metrics["roas"],
                ",".join(_anomaly_flags(metrics)) or "none",
            )
            for row in channel_rows
            for metrics in [
                _compute_metrics(
                    spend=row["spend"] or 0.0,
                    impressions=row["impressions"] or 0,
                    clicks=row["clicks"] or 0,
                    conversions=row["conversions"] or 0,
                    revenue=row["revenue"] or 0.0,
                )
            ]
        ],
    )
    conn.commit()


def _insert_rejection(
    conn: sqlite3.Connection,
    bronze_id: int,
    event_id: str | None,
    reason: str,
    payload_json: str,
) -> None:
    conn.execute(
        """
        INSERT INTO rejected_events (bronze_id, event_id, reason, payload_json, rejected_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (bronze_id, event_id, reason, payload_json, utc_now_iso()),
    )


def _coerce_float(value: Any, field: str, errors: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"invalid_{field}")
        return None


def _parse_iso(value: Any, field: str, errors: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        errors.append(f"invalid_{field}")
        return None


def _format_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _compute_metrics(
    spend: float,
    impressions: int,
    clicks: int,
    conversions: int,
    revenue: float,
) -> dict[str, Any]:
    return {
        "spend": round(spend, 2),
        "impressions": int(impressions),
        "clicks": int(clicks),
        "conversions": int(conversions),
        "revenue": round(revenue, 2),
        "ctr": _safe_divide(clicks, impressions),
        "cpc": _safe_divide(spend, clicks),
        "cpa": _safe_divide(spend, conversions),
        "roas": _safe_divide(revenue, spend),
    }


def _anomaly_flags(metrics: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if metrics["spend"] > 100 and metrics["clicks"] == 0:
        flags.append("spend_without_clicks")
    if metrics["impressions"] >= 200 and metrics["ctr"] < 0.008:
        flags.append("low_ctr")
    if metrics["spend"] >= 80 and metrics["roas"] < 0.75:
        flags.append("low_roas")
    if metrics["conversions"] > 0 and metrics["cpa"] > 95:
        flags.append("high_cpa")
    return flags
