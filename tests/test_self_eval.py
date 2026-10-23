"""Self-eval stops on a pass, on a stall, or on the cap."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from self_eval import decide, main, project_note  # noqa: E402


class SelfEvalTests(unittest.TestCase):
    def test_stop_when_the_checks_pass(self):
        passes = [{"failures": ["caption"] }, {"failures": []}]
        self.assertEqual(decide(passes, 3), "stop_pass")

    def test_stop_when_a_pass_changes_nothing(self):
        stalled = [{"failures": ["eyes"]}, {"failures": ["eyes"]}]
        self.assertEqual(decide(stalled, 3), "stop_no_progress")

    def test_cap_is_a_backstop(self):
        moving = [
            {"failures": ["a"]},
            {"failures": ["b"]},
            {"failures": ["c"]},
        ]
        self.assertEqual(decide(moving, 3), "stop_cap")
        self.assertEqual(decide(moving[:2], 3), "rerender")

    def test_note_keeps_the_remaining_issues(self):
        note = project_note([{"failures": ["eyes"], "loudness": "-14 LUFS"}], "stop_cap")
        self.assertIn("eyes", note)
        self.assertIn("-14 LUFS", note)
        self.assertIn("preview", note)

    def test_cli_appends_the_note(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            passes = folder / "passes.json"
            passes.write_text('[{"failures": ["same"]}, {"failures": ["same"]}]')
            project = folder / "project.md"
            code = main(["--passes", str(passes), "--max-passes", "3", "--project", str(project)])
            self.assertEqual(code, 0)
            text = project.read_text()
        self.assertIn("stop_no_progress", text)
        self.assertIn("preview", text)


if __name__ == "__main__":
    unittest.main()
