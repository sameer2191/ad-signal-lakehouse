# Data Contract

The bronze stream contains one JSON object per line. Required fields are validated before a row can enter silver.

## Required Event Fields

| Field | Type | Description |
| --- | --- | --- |
| `event_id` | string | Unique event identifier from the source platform |
| `event_ts` | ISO-8601 timestamp | Business event timestamp |
| `ingest_ts` | ISO-8601 timestamp | Time the event arrived in the pipeline |
| `event_type` | enum | `impression`, `click`, `conversion`, or `spend` |
| `channel` | enum | One of the configured marketing channels |
| `campaign_id` | string | Stable campaign key |
| `campaign_name` | string | Human-readable campaign name |
| `user_id` | string | Synthetic anonymous user key |
| `cost_usd` | number | Spend amount for spend events, otherwise `0.0` |
| `revenue_usd` | number | Conversion revenue for conversion events, otherwise `0.0` |

## Optional Event Fields

| Field | Type | Description |
| --- | --- | --- |
| `device` | string | Synthetic device segment |
| `geo` | string | Synthetic US region code |
| `placement` | string | Synthetic ad placement |
| `source` | string | Source system label |

## Validation Rules

- All required fields must be present.
- `event_ts` and `ingest_ts` must parse as timestamps.
- `event_type` must be one of the supported values.
- `channel` must be one of the configured channels.
- `cost_usd` and `revenue_usd` must be numeric.
- Negative spend and negative revenue are rejected.
- A row is flagged late when `ingest_ts - event_ts > 24 hours`.
- Duplicate `event_id` values are accepted into silver with `is_duplicate = 1` but excluded from gold.

## Rejection Handling

Rejected rows are written to `rejected_events` with:

- `bronze_id`
- source `event_id` when available
- comma-separated rejection reason
- full raw payload
- rejection timestamp

This preserves enough context to debug source regressions without weakening silver table contracts.
