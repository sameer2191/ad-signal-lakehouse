# Architecture

Ad Signal Lakehouse is a local-first implementation of a medallion analytics pipeline. It is intentionally small enough to run anywhere, while still modeling the control points of a production marketing data platform.

## Components

| Layer | Implementation | Responsibility |
| --- | --- | --- |
| Generator | `src/ad_signal_lakehouse/generator.py` | Creates deterministic ad impressions, clicks, conversions, and spend events |
| Bronze | JSONL + `bronze_events` | Preserves raw payloads with file and line lineage |
| Silver | `silver_events`, `rejected_events` | Validates schema, types, timestamps, spend/revenue guards, duplicates, and late arrivals |
| Gold | `gold_campaign_daily`, `gold_channel_daily` | Produces daily KPI marts for analytics consumers |
| Observability | `reports/pipeline_health.json` | Publishes row counts, reject reasons, rates, and quality gate status |
| Dashboard | `dashboard/index.html` | Provides a portable executive and anomaly summary |

## Flow

1. `python -m ad_signal_lakehouse demo` calls the deterministic event generator.
2. Raw payloads are written to a run-specific file such as `bronze/ad_events_seed42_n5000.jsonl`.
3. The same raw file is loaded into SQLite `bronze_events` with line-level lineage.
4. Each raw payload is parsed and validated.
5. Valid rows land in `silver_events`; invalid rows land in `rejected_events`.
6. Gold transforms aggregate accepted, non-duplicate rows by date/channel/campaign.
7. Quality gates summarize whether the run is trustworthy enough to publish.
8. The dashboard reads curated gold tables and the health report.

## Local Design Choices

- SQLite keeps the project runnable with standard Python and no service accounts.
- JSONL mirrors common object-storage ingestion patterns while staying inspectable in GitHub demos.
- The generator is deterministic by seed, making demos and tests reproducible.
- Rejected payloads are retained so quality failures can be debugged without re-running ingestion.
- Gold tables exclude duplicates, but silver keeps duplicate flags for lineage and auditability.

## Production Mapping

| Local project | Production analogue |
| --- | --- |
| JSONL file | Kafka/Redpanda topic, object storage landing zone |
| SQLite bronze table | external/raw table over object storage |
| SQLite silver/gold SQL | dbt, Spark SQL, Snowflake tasks, BigQuery SQL |
| Health JSON | orchestration metadata, data quality observability |
| Static dashboard | BI extract, Evidence app, Looker dashboard |

The point of the repo is not to pretend SQLite is a cloud lakehouse. It is to show the modeling, validation, transformation, and operational judgment that transfers to larger stacks.
