# Ad Signal Lakehouse

Local marketing analytics lakehouse simulator for reproducible campaign-performance pipelines.

This project builds a full bronze/silver/gold pipeline without cloud accounts, external services, network access, or third-party Python packages. It generates deterministic synthetic ad-platform events, lands append-only JSONL, validates and normalizes records into SQLite, computes campaign KPIs, runs quality gates, and emits a static dashboard artifact.

## Pipeline Capabilities

Ad Signal Lakehouse covers the core mechanics of a modern marketing data platform:

- batch ingestion with immutable raw files
- schema validation, reject handling, duplicate detection, and late-event flags
- medallion modeling from raw event streams to analytics-ready marts
- KPI transformations for paid media reporting
- quality gates and pipeline health reporting
- reproducible local demos and CI using only Python standard library + SQLite
- dashboard artifact generation from curated gold tables

## Architecture

```text
Synthetic generator
      |
      v
Bronze JSONL
append-only ad event records
      |
      v
SQLite bronze_events
raw payload lineage by source file + line
      |
      v
SQLite silver_events + rejected_events
schema validation, negative spend guard, duplicate ids, late-event flags
      |
      v
SQLite gold_campaign_daily + gold_channel_daily
spend, impressions, clicks, conversions, CTR, CPC, CPA, ROAS, anomaly flags
      |
      v
reports/pipeline_health.json + dashboard/index.html
```

See [docs/architecture.md](docs/architecture.md) for deeper design notes.

## Quickstart

From the repository root:

```bash
python -m ad_signal_lakehouse demo --output runs/demo --events 5000
python -m unittest discover -s tests
```

The repo uses a conventional `src/` package layout and includes a tiny root-level import shim so the exact `python -m ad_signal_lakehouse ...` command works locally without installing the package. If you prefer an installed command, run `python -m pip install -e .` and then use `ad-signal-lakehouse demo`.

## Demo Outputs

The demo writes:

| Artifact | Path | Purpose |
| --- | --- | --- |
| Bronze JSONL | `runs/demo/bronze/ad_events_seed42_n5000.jsonl` | Raw generated event stream with source fidelity |
| SQLite database | `runs/demo/lakehouse.db` | Bronze, silver, rejected, and gold tables |
| Health report | `runs/demo/reports/pipeline_health.json` | Counts, rates, reject reasons, quality gates |
| Static dashboard | `runs/demo/dashboard/index.html` | Portable HTML summary of KPIs and anomalies |

Example CLI output:

```text
Ad Signal Lakehouse demo complete
  status: pass
  output: runs/demo
  bronze: runs/demo/bronze/ad_events_seed42_n5000.jsonl
  sqlite: runs/demo/lakehouse.db
  health: runs/demo/reports/pipeline_health.json
  dashboard: runs/demo/dashboard/index.html
  counts: bronze=5000, silver=4998, rejected=2, duplicates=1, late=1
```

Actual counts are deterministic for a given `--events` and `--seed`.

## KPI Table

Gold tables compute daily channel and campaign metrics:

| Metric | Definition | Guardrail |
| --- | --- | --- |
| `spend` | Sum of valid spend-event `cost_usd` | Negative spend rejected before silver |
| `impressions` | Count of valid `impression` events | Duplicate event ids excluded from gold |
| `clicks` | Count of valid `click` events | Duplicate event ids excluded from gold |
| `conversions` | Count of valid `conversion` events | Duplicate event ids excluded from gold |
| `revenue` | Sum of conversion `revenue_usd` | Negative revenue rejected |
| `ctr` | `clicks / impressions` | Safe divide returns `0.0` |
| `cpc` | `spend / clicks` | Safe divide returns `0.0` |
| `cpa` | `spend / conversions` | Safe divide returns `0.0` |
| `roas` | `revenue / spend` | Safe divide returns `0.0` |
| `anomaly_flags` | Rule-based flags for suspicious KPI rows | Stored in gold marts |

## Realistic Failure Modes

The deterministic generator injects production-like edge cases:

- duplicate event ids
- late-arriving events
- negative spend rows
- schema violations
- zero-denominator KPI scenarios

The pipeline preserves rejected payloads in `rejected_events`, flags duplicates and late rows in `silver_events`, and excludes invalid/duplicate records from gold aggregations.

## Useful SQLite Queries

```bash
sqlite3 runs/demo/lakehouse.db "select * from gold_channel_daily limit 10;"
sqlite3 runs/demo/lakehouse.db "select reason, count(*) from rejected_events group by reason;"
sqlite3 runs/demo/lakehouse.db "select campaign_name, spend, roas, anomaly_flags from gold_campaign_daily where anomaly_flags <> 'none' order by spend desc;"
```

## Optional Production Extensions

The local design maps cleanly to managed data stacks:

- Kafka or Redpanda topic in place of generated JSONL
- object storage for bronze event files
- Snowflake, BigQuery, Databricks, or DuckDB in place of SQLite
- dbt models for silver/gold transformations
- Great Expectations, Soda, or dbt tests for quality gates
- BI surfaces such as Looker, Hex, Mode, Tableau, or Evidence

These are intentionally optional. The committed tests and demo require only Python 3.

## Project Layout

```text
src/ad_signal_lakehouse/
  cli.py          command line entrypoint
  generator.py    deterministic synthetic event generator
  lakehouse.py    medallion pipeline and SQLite transformations
  quality.py      quality gates and health report
  dashboard.py    static HTML dashboard writer
docs/
  architecture.md
  data_contract.md
  quality_gates.md
tests/
  test_generator.py
  test_pipeline.py
```

## Development

Run the same checks used by CI:

```bash
python -m unittest discover -s tests
python -m ad_signal_lakehouse demo --output runs/dev --events 1000
```

No secrets are required. `.env.example` documents optional local defaults only.
