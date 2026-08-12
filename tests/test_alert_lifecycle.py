import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from alert_lifecycle import read_events, serializable, simulate


class AlertLifecycleTests(unittest.TestCase):
    def test_duplicate_delivery_is_idempotent_in_notification_count(self):
        events = [{"subject": "alpha", "kind": "degraded", "fingerprint": "x", "at": "same"}] * 2
        result = simulate(events)
        self.assertEqual(result["digest"]["notifications"], 1)
        self.assertEqual(result["digest"]["transitions"], 1)

    def test_recovery_then_recurrence_reopens(self):
        events = [
            {"subject": "alpha", "kind": "degraded", "fingerprint": "x"},
            {"subject": "alpha", "kind": "healthy", "fingerprint": "clear"},
            {"subject": "alpha", "kind": "degraded", "fingerprint": "x"},
        ]
        result = simulate(events)
        self.assertEqual(result["digest"]["notifications"], 2)
        self.assertEqual(result["states"]["alpha"].state, "degraded")

    def test_acknowledgement_suppresses_unchanged_condition(self):
        events = [
            {"subject": "alpha", "kind": "degraded", "fingerprint": "x"},
            {"subject": "alpha", "kind": "degraded", "fingerprint": "x"},
        ]
        result = simulate(events, acknowledgements={"alpha"})
        self.assertEqual(result["states"]["alpha"].acknowledged, True)
        self.assertEqual(result["digest"]["notifications"], 1)

    def test_changed_fingerprint_pages_again(self):
        events = [
            {"subject": "alpha", "kind": "degraded", "fingerprint": "x"},
            {"subject": "alpha", "kind": "degraded", "fingerprint": "y"},
        ]
        self.assertEqual(simulate(events)["digest"]["notifications"], 2)

    def test_digest_has_only_safe_worklist_fields(self):
        result = serializable(simulate(read_events(Path(__file__).parents[1] / "fixtures" / "events.jsonl")))
        self.assertEqual(set(result["digest"]["worklist"][0]), {"subject", "state", "acknowledged", "notifications", "latest_reason"})
        self.assertNotIn("url", json.dumps(result))

    def test_invalid_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate([{"subject": "alpha", "kind": "unknown", "fingerprint": "x"}])


if __name__ == "__main__":
    unittest.main()
