import csv
import re
import json
import time
import unittest
from pathlib import Path
from app.schemas import TriageRequest
from app.core.pipeline import run_triage_pipeline
from app.core.triage_model import predict_triage, load_artifacts

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"
UNSEEN_TESTS = BASE_DIR / "ml" / "data" / "unseen_tests.csv"
REDFLAG_TESTS = BASE_DIR / "ml" / "data" / "redflag_tests.csv"
RESULTS_FILE = BASE_DIR / "ml" / "results" / "comparison.json"


class TestModelCardAndBenchmarks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        load_artifacts()

    def test_no_estimated_or_untrained_numbers_in_model_comparison(self):
        """Fails if docs/MODEL_COMPARISON.md contains 'Estimated' or any number in an untrained row."""
        comp_file = DOCS_DIR / "MODEL_COMPARISON.md"
        self.assertTrue(comp_file.exists(), f"Missing {comp_file}")

        content = comp_file.read_text(encoding="utf-8")
        self.assertNotIn("estimated", content.lower(), "MODEL_COMPARISON.md must not contain 'Estimated' numbers.")

        # Check Model E untrained row has NO numbers
        lines = content.splitlines()
        model_e_lines = [l for l in lines if "Model E:" in l]
        self.assertTrue(len(model_e_lines) > 0, "Model E row must exist in comparison table.")
        for l in model_e_lines:
            cells = [c.strip() for c in l.split("|")[1:-1]]
            for c in cells[1:]:
                digits = re.findall(r"\d+", c)
                self.assertEqual(len(digits), 0, f"Untrained row for Model E contains numbers: {c}")

    def test_winning_model_probabilities_sum_to_one_on_all_30_unseen_tests(self):
        """Tests that the winning model's probabilities sum to 1 (+-1e-5) on all 30 unseen test inputs."""
        self.assertTrue(UNSEEN_TESTS.exists(), f"Missing {UNSEEN_TESTS}")

        unseen_inputs = []
        with open(UNSEEN_TESTS, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unseen_inputs.append(row["user_input"])

        self.assertEqual(len(unseen_inputs), 30, f"Expected exactly 30 unseen test inputs, got {len(unseen_inputs)}")

        for text in unseen_inputs:
            slots = {}
            res = predict_triage(slots, text)
            care_pred, urgency, probs, conf, top_terms, nearest_examples = res

            prob_sum = sum(probs.values())
            self.assertAlmostEqual(
                prob_sum,
                1.0,
                delta=1e-5,
                msg=f"Probabilities must sum to 1.0 (+-1e-5) for input '{text}', got {prob_sum}"
            )
            self.assertTrue(all(0.0 <= p <= 1.0 for p in probs.values()), f"Probabilities out of bounds: {probs}")

    def test_classifier_predicts_under_50ms_on_cpu(self):
        """Tests that inference latency on CPU is strictly < 50ms per request."""
        slots = {"symptoms": ["fever"], "patient_relation": "self"}
        text = "mummy ka bp sugar ghar pe check karwana hai"

        # Warmup
        _ = predict_triage(slots, text)

        # Benchmark 10 runs
        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            _ = predict_triage(slots, text)
            latencies.append((time.perf_counter() - t0) * 1000)

        avg_latency = sum(latencies) / len(latencies)
        print(f"\n[BENCHMARK] Average CPU inference latency: {avg_latency:.2f} ms")
        self.assertLess(avg_latency, 50.0, f"Inference latency exceeded 50ms limit: {avg_latency:.2f} ms")

    def test_explainability_returns_non_empty_results(self):
        """Tests that explainability (nearest training examples + keywords) works and returns non-empty results."""
        text = "ghar pe injection lagwana hai"
        slots = {}
        care_pred, urgency, probs, conf, top_terms, nearest_examples = predict_triage(slots, text)

        self.assertIsInstance(top_terms, list)
        self.assertGreater(len(top_terms), 0, "Top terms list must not be empty.")
        self.assertIn("term", top_terms[0])
        self.assertIn("weight", top_terms[0])

        self.assertIsInstance(nearest_examples, list)
        self.assertGreater(len(nearest_examples), 0, "Nearest examples list must not be empty.")
        self.assertIn("text", nearest_examples[0])
        self.assertIn("care_type", nearest_examples[0])
        self.assertIn("similarity", nearest_examples[0])

        # Test pipeline debug mode integration
        req = TriageRequest(
            user_input=text,
            conversation_history=[],
            context_consent=False
        )
        resp = run_triage_pipeline(req, debug=True)
        self.assertIsNotNone(resp.debug, "Debug trace must be populated when debug=True")
        self.assertIn("top_terms", resp.debug)
        self.assertIn("nearest_examples", resp.debug)
        self.assertIn("calibrated_probabilities", resp.debug)

        # Verify user reasoning does not leak raw weights or floats
        self.assertNotIn("0.", resp.reasoning)
        self.assertNotIn("weight", resp.reasoning)

    def test_small_cluster_validation_invariants(self):
        """Tests that small-cluster grouping produced >= 50 groups and recorded leave-one-cluster-out recall."""
        self.assertTrue(RESULTS_FILE.exists(), f"Missing {RESULTS_FILE}")
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        selection = data.get("_selection", {})
        self.assertIn("small_cluster_groups", selection)
        self.assertGreaterEqual(selection["small_cluster_groups"], 50)
        self.assertIn("leave_one_cluster_out_mean_recall", selection)
        self.assertGreaterEqual(selection["leave_one_cluster_out_mean_recall"], 0.80)

    def test_reviewed_by_human_column_present(self):
        """Tests that evaluation benchmarks track reviewed_by_human flag and have a team review README."""
        for path in [UNSEEN_TESTS, REDFLAG_TESTS]:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertIn("reviewed_by_human", reader.fieldnames, f"{path} missing reviewed_by_human column")

        readme = BASE_DIR / "ml" / "data" / "README.md"
        self.assertTrue(readme.exists(), "Missing ml/data/README.md")
        content = readme.read_text(encoding="utf-8")
        self.assertIn("clinical", content.lower())


if __name__ == "__main__":
    unittest.main()
