import csv
import re
import time
import unittest
from pathlib import Path
from app.schemas import TriageRequest
from app.core.pipeline import run_triage_pipeline
from app.core.triage_model import predict_triage, load_artifacts

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"
UNSEEN_TESTS = BASE_DIR / "ml" / "data" / "unseen_tests.csv"


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
            # Model E row should say 'NOT RUN' across metric columns and have no digits in metrics
            cells = [c.strip() for c in l.split("|")[1:-1]]
            # Ensure cell 1 to 9 (metrics) do not contain numbers
            for c in cells[1:]:
                # If cell is not empty, check it doesn't contain numeric digits
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


if __name__ == "__main__":
    unittest.main()
