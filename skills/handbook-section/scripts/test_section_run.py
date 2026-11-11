"""Offline behavioral checks for recovery, scope and attempt accounting."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).with_name("section_run.py")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.schema = {"folders": {"demo": {"articles": [
            {"file": "01-example.md", "status": "draft"}]}}}
        self.write_schema()
        (self.root / "AUTHORING_GUIDE.md").write_text("Guide\n")
        (self.root / "prompt.md").write_text("Actual prompt\n")
        (self.root / "result.json").write_text('{"verdict":"changes_requested"}')
        self.article = "content/demo/01-example.md"
        (self.root / self.article).parent.mkdir(parents=True)
        (self.root / self.article).write_text("English\n")

    def write_schema(self):
        (self.root / "schema.yaml").write_text(yaml.safe_dump(self.schema))

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root),
                                 *args], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(result.stdout) if ok else result.stderr

    def start(self, kind="source", **kwargs):
        return self.cli("start", "demo", "--kind", kind, "--provider", "test",
                        "--model", "offline", "--approval", "fixture only",
                        "--input", "prompt.md", **kwargs)

    def finish(self, outcome="completed"):
        return self.cli("finish", "demo", "--outcome", outcome,
                        "--artifact", "result.json", "--note", "Offline fixture",
                        "--next-step", "Inspect findings")

    def test_init_is_non_destructive_and_budget_scoped(self):
        result = self.cli("init", "demo")
        self.assertEqual(result["budget"], 7)
        manifest = self.root / result["manifest"]
        before = manifest.read_bytes()
        self.cli("init", "demo", ok=False)
        self.assertEqual(manifest.read_bytes(), before)

    def test_pending_call_survives_new_process_and_prevents_duplicate(self):
        self.cli("init", "demo")
        self.start()
        self.assertEqual(self.cli("status", "demo")["pending"], [1])
        self.start(ok=False)
        self.assertEqual(self.cli("status", "demo")["attempts"], 1)

    def test_failed_and_unknown_attempts_consume_budget(self):
        self.cli("init", "demo", "--call-budget", "2")
        for outcome in ("failed", "unknown"):
            self.start("plan")
            self.finish(outcome)
        self.start("plan", ok=False)
        self.assertEqual(self.cli("status", "demo")["attempts"], 2)

    def test_batch_review_cap_counts_each_attempt(self):
        self.cli("init", "demo", "--call-budget", "10")
        for _ in range(2):
            self.start()
            self.finish("failed")
        self.start(ok=False)
        self.assertEqual(self.cli("status", "demo")["attempts"], 2)

    def test_existing_manifest_retains_legacy_review_cap(self):
        result = self.cli("init", "demo")
        path = self.root / result['manifest']
        data = json.loads(path.read_text())
        data.pop('review_pass_limit')
        data.pop('profile')
        path.write_text(json.dumps(data))
        for _ in range(3):
            self.start()
            self.finish('failed')
        self.start(ok=False)

    def test_recovery_attachment_preserves_call_and_budget(self):
        self.cli('init', 'demo')
        self.start()
        self.cli('attach', 'demo', '--call', '1', '--artifact', 'result.json', '--note', 'Reparse', ok=False)
        self.finish()
        result = self.cli('attach', 'demo', '--call', '1', '--artifact', 'result.json', '--note', 'Reparse')
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(result['budget'], 7)
        manifest = json.loads((self.root / result['manifest']).read_text())
        self.assertEqual(len(manifest['calls'][0]['recoveries']), 1)

    def test_changed_inputs_are_visible_without_certifying_acceptance(self):
        self.cli("init", "demo")
        self.start()
        self.finish()
        (self.root / self.article).write_text("Changed English\n")
        result = self.cli("status", "demo")
        self.assertIn({"call": 1, "input": self.article}, result["changed_inputs"])
        self.assertNotIn("accepted", result)

    def test_invalid_inputs_do_not_consume_call(self):
        self.cli("init", "demo")
        self.cli("start", "demo", "--kind", "plan", "--provider", "test",
                 "--model", "offline", "--approval", "fixture",
                 "--input", "../outside", ok=False)
        self.start("bilingual", ok=False)  # Swedish missing
        self.assertEqual(self.cli("status", "demo")["attempts"], 0)

    def test_unscaffolded_section_can_plan_then_enroll_without_reset(self):
        self.schema["folders"]["demo"] = {"legacy_articles": 4}
        self.write_schema()
        self.assertEqual(self.cli("init", "demo")["budget"], 13)
        self.start(ok=False)
        self.start("plan")
        self.finish()
        self.schema["folders"]["demo"]["articles"] = [{"file": "01-example.md"}]
        self.write_schema()
        result = self.cli("enroll", "demo", "--article", "01-example.md")
        self.assertEqual(result["articles"], [self.article])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["budget"], 13)


if __name__ == "__main__":
    unittest.main()
