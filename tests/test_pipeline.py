from pathlib import Path
import sqlite3
import tempfile
import unittest

from ad_signal_lakehouse.lakehouse import run_demo, validate_event


class PipelineTests(unittest.TestCase):
    def test_validate_event_rejects_negative_spend(self):
        payload = {
            "event_id": "evt_bad",
            "event_ts": "2026-06-01T00:00:00Z",
            "ingest_ts": "2026-06-01T00:02:00Z",
            "event_type": "spend",
            "channel": "paid_search",
            "campaign_id": "SEA_BRAND_US",
            "campaign_name": "US Brand Search",
            "user_id": "user_1",
            "cost_usd": -1.0,
            "revenue_usd": 0.0,
        }
        _, errors = validate_event(payload)
        self.assertIn("negative_spend", errors)

    def test_demo_builds_artifacts_and_quality_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp) / "demo", events=400, seed=123)
            self.assertEqual(result.status, "pass")
            self.assertTrue(result.bronze_file.exists())
            self.assertTrue(result.database_path.exists())
            self.assertTrue(result.health_report_path.exists())
            self.assertTrue(result.dashboard_path.exists())
            self.assertEqual(result.counts["bronze_events"], 400)
            self.assertGreater(result.counts["silver_events"], 0)
            self.assertGreaterEqual(result.counts["rejected_events"], 2)
            self.assertGreaterEqual(result.counts["duplicate_events"], 1)
            self.assertGreaterEqual(result.counts["late_events"], 1)

    def test_gold_metrics_are_safe_and_non_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp) / "demo", events=250, seed=55)
            with sqlite3.connect(result.database_path) as conn:
                rows = conn.execute(
                    """
                    SELECT spend, ctr, cpc, cpa, roas
                    FROM gold_campaign_daily
                    """
                ).fetchall()
            self.assertTrue(rows)
            for spend, ctr, cpc, cpa, roas in rows:
                self.assertGreaterEqual(spend, 0.0)
                self.assertGreaterEqual(ctr, 0.0)
                self.assertGreaterEqual(cpc, 0.0)
                self.assertGreaterEqual(cpa, 0.0)
                self.assertGreaterEqual(roas, 0.0)


if __name__ == "__main__":
    unittest.main()
