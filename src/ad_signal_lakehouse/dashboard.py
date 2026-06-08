"""Static dashboard artifact generation."""

from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3
from typing import Any


def render_dashboard(
    conn: sqlite3.Connection,
    health_report: dict[str, Any],
    output_path: Path,
    database_path: Path,
    bronze_file: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    campaign_rows = conn.execute(
        """
        SELECT *
        FROM gold_campaign_daily
        ORDER BY spend DESC, revenue DESC
        LIMIT 15
        """
    ).fetchall()
    channel_rows = conn.execute(
        """
        SELECT
            channel,
            SUM(spend) AS spend,
            SUM(impressions) AS impressions,
            SUM(clicks) AS clicks,
            SUM(conversions) AS conversions,
            SUM(revenue) AS revenue,
            CASE WHEN SUM(impressions) = 0 THEN 0.0 ELSE CAST(SUM(clicks) AS REAL) / SUM(impressions) END AS ctr,
            CASE WHEN SUM(clicks) = 0 THEN 0.0 ELSE SUM(spend) / SUM(clicks) END AS cpc,
            CASE WHEN SUM(conversions) = 0 THEN 0.0 ELSE SUM(spend) / SUM(conversions) END AS cpa,
            CASE WHEN SUM(spend) = 0 THEN 0.0 ELSE SUM(revenue) / SUM(spend) END AS roas
        FROM gold_channel_daily
        GROUP BY channel
        ORDER BY spend DESC
        """
    ).fetchall()
    anomaly_rows = conn.execute(
        """
        SELECT event_date, channel, campaign_name, spend, ctr, cpa, roas, anomaly_flags
        FROM gold_campaign_daily
        WHERE anomaly_flags <> 'none'
        ORDER BY spend DESC
        LIMIT 10
        """
    ).fetchall()

    totals = _totals(channel_rows)
    max_channel_spend = max((row["spend"] or 0.0 for row in channel_rows), default=1.0)
    max_campaign_spend = max((row["spend"] or 0.0 for row in campaign_rows), default=1.0)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ad Signal Lakehouse Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5e6b78;
      --line: #d9e1e8;
      --panel: #ffffff;
      --soft: #f5f7fa;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #eef2f6;
      color: var(--ink);
    }}
    header {{
      padding: 28px 32px 20px;
      background: #17202a;
      color: #fff;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 0; color: #d8e0e8; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 18px;
    }}
    .grid {{ display: grid; gap: 14px; grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .metric {{
      background: var(--soft);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .metric .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bar-track {{ width: 100%; height: 8px; background: #dbe4ec; border-radius: 4px; overflow: hidden; }}
    .bar {{ height: 8px; background: var(--accent); border-radius: 4px; }}
    .status-pass {{ color: var(--accent); font-weight: 700; }}
    .status-fail {{ color: var(--bad); font-weight: 700; }}
    .flag {{ color: var(--warn); font-weight: 700; }}
    .artifact {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
    @media (max-width: 850px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      main {{ padding: 16px; }}
      table {{ font-size: 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Ad Signal Lakehouse Dashboard</h1>
    <p>Local medallion pipeline output for synthetic paid marketing events.</p>
  </header>
  <main>
    <section>
      <h2>Executive KPI Snapshot</h2>
      <div class="grid">
        {_metric_card("Spend", _money(totals["spend"]))}
        {_metric_card("Revenue", _money(totals["revenue"]))}
        {_metric_card("ROAS", _ratio(totals["roas"]))}
        {_metric_card("Conversions", _integer(totals["conversions"]))}
      </div>
      <div class="artifact">Health: <span class="status-{escape(health_report["status"])}">{escape(health_report["status"].upper())}</span> · Generated {escape(health_report["generated_at"])} · DB {escape(str(database_path))} · Bronze {escape(str(bronze_file))}</div>
    </section>

    <section>
      <h2>Channel Performance</h2>
      <table>
        <thead><tr><th>Channel</th><th class="num">Spend</th><th>Spend Mix</th><th class="num">Impr.</th><th class="num">Clicks</th><th class="num">Conv.</th><th class="num">CTR</th><th class="num">CPA</th><th class="num">ROAS</th></tr></thead>
        <tbody>
          {''.join(_channel_row(row, max_channel_spend) for row in channel_rows)}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Top Campaign Daily Rows</h2>
      <table>
        <thead><tr><th>Date</th><th>Campaign</th><th>Channel</th><th class="num">Spend</th><th>Spend Bar</th><th class="num">Clicks</th><th class="num">Conv.</th><th class="num">CPA</th><th class="num">ROAS</th><th>Flags</th></tr></thead>
        <tbody>
          {''.join(_campaign_row(row, max_campaign_spend) for row in campaign_rows)}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Quality Gates</h2>
      <table>
        <thead><tr><th>Gate</th><th>Status</th><th>Description</th></tr></thead>
        <tbody>
          {''.join(_quality_gate_row(gate) for gate in health_report["quality_gates"])}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Anomaly Watchlist</h2>
      <table>
        <thead><tr><th>Date</th><th>Campaign</th><th>Channel</th><th class="num">Spend</th><th class="num">CTR</th><th class="num">CPA</th><th class="num">ROAS</th><th>Flags</th></tr></thead>
        <tbody>
          {''.join(_anomaly_row(row) for row in anomaly_rows) or '<tr><td colspan="8">No campaign anomalies detected.</td></tr>'}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _totals(channel_rows) -> dict[str, float]:
    spend = sum(float(row["spend"] or 0.0) for row in channel_rows)
    revenue = sum(float(row["revenue"] or 0.0) for row in channel_rows)
    impressions = sum(int(row["impressions"] or 0) for row in channel_rows)
    clicks = sum(int(row["clicks"] or 0) for row in channel_rows)
    conversions = sum(int(row["conversions"] or 0) for row in channel_rows)
    return {
        "spend": spend,
        "revenue": revenue,
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "ctr": clicks / impressions if impressions else 0.0,
        "roas": revenue / spend if spend else 0.0,
    }


def _metric_card(label: str, value: str) -> str:
    return f'<div class="metric"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div></div>'


def _channel_row(row, max_spend: float) -> str:
    spend = float(row["spend"] or 0.0)
    width = 0 if max_spend == 0 else int((spend / max_spend) * 100)
    return f"""
    <tr>
      <td>{escape(str(row["channel"]))}</td>
      <td class="num">{_money(spend)}</td>
      <td><div class="bar-track"><div class="bar" style="width: {width}%"></div></div></td>
      <td class="num">{_integer(row["impressions"])}</td>
      <td class="num">{_integer(row["clicks"])}</td>
      <td class="num">{_integer(row["conversions"])}</td>
      <td class="num">{_percent(row["ctr"])}</td>
      <td class="num">{_money(row["cpa"])}</td>
      <td class="num">{_ratio(row["roas"])}</td>
    </tr>
    """


def _campaign_row(row, max_spend: float) -> str:
    spend = float(row["spend"] or 0.0)
    width = 0 if max_spend == 0 else int((spend / max_spend) * 100)
    flags = str(row["anomaly_flags"])
    flag_class = "flag" if flags != "none" else ""
    return f"""
    <tr>
      <td>{escape(str(row["event_date"]))}</td>
      <td>{escape(str(row["campaign_name"]))}</td>
      <td>{escape(str(row["channel"]))}</td>
      <td class="num">{_money(spend)}</td>
      <td><div class="bar-track"><div class="bar" style="width: {width}%"></div></div></td>
      <td class="num">{_integer(row["clicks"])}</td>
      <td class="num">{_integer(row["conversions"])}</td>
      <td class="num">{_money(row["cpa"])}</td>
      <td class="num">{_ratio(row["roas"])}</td>
      <td class="{flag_class}">{escape(flags)}</td>
    </tr>
    """


def _quality_gate_row(gate: dict[str, Any]) -> str:
    status = "pass" if gate["passed"] else "fail"
    return f"""
    <tr>
      <td>{escape(gate["name"])}</td>
      <td class="status-{status}">{status.upper()}</td>
      <td>{escape(gate["description"])}</td>
    </tr>
    """


def _anomaly_row(row) -> str:
    return f"""
    <tr>
      <td>{escape(str(row["event_date"]))}</td>
      <td>{escape(str(row["campaign_name"]))}</td>
      <td>{escape(str(row["channel"]))}</td>
      <td class="num">{_money(row["spend"])}</td>
      <td class="num">{_percent(row["ctr"])}</td>
      <td class="num">{_money(row["cpa"])}</td>
      <td class="num">{_ratio(row["roas"])}</td>
      <td class="flag">{escape(str(row["anomaly_flags"]))}</td>
    </tr>
    """


def _money(value: Any) -> str:
    return f"${float(value or 0.0):,.2f}"


def _integer(value: Any) -> str:
    return f"{int(value or 0):,}"


def _percent(value: Any) -> str:
    return f"{float(value or 0.0) * 100:.2f}%"


def _ratio(value: Any) -> str:
    return f"{float(value or 0.0):.2f}x"
