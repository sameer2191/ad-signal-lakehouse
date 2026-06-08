# Quality Gates

Quality gates are generated in `reports/pipeline_health.json` after every demo run.

## Gates

| Gate | Pass Condition | Why It Matters |
| --- | --- | --- |
| `bronze_loaded` | Bronze row count is greater than zero | Confirms source ingestion worked |
| `silver_loaded` | Silver row count is greater than zero | Confirms usable validated data exists |
| `reject_rate_under_5_percent` | Rejected rows are at most 5 percent of bronze | Detects schema drift and upstream regressions |
| `duplicate_rate_under_5_percent` | Duplicate ids are at most 5 percent of silver | Detects replay or idempotency failures |
| `negative_spend_blocked` | No negative spend reaches silver | Protects financial metrics |
| `gold_built` | Gold campaign rows are greater than zero | Confirms analytics marts were produced |

## Report Shape

```json
{
  "status": "pass",
  "generated_at": "2026-06-01T12:00:00Z",
  "counts": {
    "bronze_events": 5000,
    "silver_events": 4998,
    "rejected_events": 2,
    "duplicate_events": 1,
    "late_events": 1
  },
  "rates": {
    "reject_rate": 0.0004,
    "duplicate_rate": 0.0002,
    "late_event_rate": 0.0002
  },
  "rejection_reasons": {
    "negative_spend": 1,
    "missing_campaign_id": 1
  },
  "quality_gates": []
}
```

## Anomaly Flags

Gold rows can include rule-based anomaly flags:

| Flag | Trigger |
| --- | --- |
| `spend_without_clicks` | Spend exceeds threshold with zero clicks |
| `low_ctr` | Large impression volume with very low CTR |
| `low_roas` | Meaningful spend with low return |
| `high_cpa` | Conversion volume exists but CPA is high |

These rules are intentionally simple and transparent. In a production system they could be replaced with historical baselines, statistical thresholds, or model-based anomaly detection.
