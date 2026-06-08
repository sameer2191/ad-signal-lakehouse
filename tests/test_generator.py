import unittest

from ad_signal_lakehouse.generator import generate_events


class GeneratorTests(unittest.TestCase):
    def test_seeded_generation_is_deterministic(self):
        first = generate_events(50, seed=99)
        second = generate_events(50, seed=99)
        self.assertEqual(first, second)

    def test_known_failure_modes_are_injected(self):
        events = generate_events(40, seed=7)
        event_ids = [event["event_id"] for event in events]
        self.assertLess(len(set(event_ids)), len(event_ids))
        self.assertTrue(any(event.get("cost_usd") == -7.25 for event in events))
        self.assertTrue(any("campaign_id" not in event for event in events))


if __name__ == "__main__":
    unittest.main()
