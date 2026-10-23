"""Per-folder installer. No network, no dependency install."""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "scripts" / "init.sh"


def _run(home, cwd, *args, extra=None):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["VIDEO_USE_HOME"] = str(ROOT)
    env["VIDEO_USE_SKIP_SYNC"] = "1"
    env.pop("ELEVENLABS_API_KEY", None)
    env.pop("CODEX_HOME", None)
    if extra:
        env.update(extra)
    return subprocess.run(
        ["bash", str(INIT), *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _links(root):
    return (
        Path(root) / ".claude" / "skills" / "video-use",
        Path(root) / ".claude" / "skills" / "style-explainer",
        Path(root) / ".agents" / "skills" / "video-use",
        Path(root) / ".agents" / "skills" / "style-explainer",
    )


class InitScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.target = Path(self.tmp.name) / "footage"
        self.target.mkdir()
        self.marker = ROOT / ".deps-installed"
        self.marker_existed = self.marker.exists()
        self.env_path = ROOT / ".env"
        self.env_before = self.env_path.read_bytes() if self.env_path.exists() else None

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(self.marker.exists(), self.marker_existed)
        after = self.env_path.read_bytes() if self.env_path.exists() else None
        self.assertEqual(after, self.env_before)

    def test_shellcheck_when_available(self):
        shellcheck = shutil.which("shellcheck")
        if shellcheck is None:
            self.skipTest("shellcheck is not installed")
        proc = subprocess.run([shellcheck, str(INIT)], check=False, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_folder_links_are_idempotent_and_remove_cleans_them(self):
        first = _run(self.home, self.target)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = _run(self.home, self.target)
        self.assertEqual(second.returncode, 0, second.stderr)
        for link, expected in zip(_links(self.target), (
            ROOT,
            ROOT / "skills" / "style-explainer",
            ROOT,
            ROOT / "skills" / "style-explainer",
        )):
            self.assertTrue(link.is_symlink(), link)
            self.assertEqual(link.resolve(), expected.resolve())
        removed = _run(self.home, self.target, "--remove")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertIn(str(self.target), removed.stdout)
        for link in _links(self.target):
            self.assertFalse(link.exists(), link)
        self.assertFalse((self.target / ".claude").exists())
        self.assertFalse((self.target / ".agents").exists())
        again = _run(self.home, self.target, "--remove")
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_global_links_home_and_existing_codex_dir(self):
        codex = self.home / ".codex" / "skills"
        codex.mkdir(parents=True)
        proc = _run(self.home, self.target, "--global")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.target / ".claude").exists())
        self.assertEqual((self.home / ".claude" / "skills" / "video-use").resolve(), ROOT.resolve())
        self.assertEqual(
            (self.home / ".agents" / "skills" / "style-explainer").resolve(),
            (ROOT / "skills" / "style-explainer").resolve(),
        )
        self.assertEqual((codex / "video-use").resolve(), ROOT.resolve())
        self.assertEqual(
            (codex / "style-explainer").resolve(),
            (ROOT / "skills" / "style-explainer").resolve(),
        )
        gone = _run(self.home, self.target, "--global", "--remove")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((self.home / ".claude").exists())
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((codex / "video-use").exists())

    def test_global_does_not_create_codex_skills(self):
        codex_root = self.home / "codex-root"
        codex_root.mkdir()
        proc = _run(self.home, self.target, "--global", extra={"CODEX_HOME": str(codex_root)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((codex_root / "skills").exists())
        self.assertTrue((self.home / ".claude" / "skills" / "video-use").is_symlink())

    def test_real_directory_is_left_alone(self):
        blocked = self.target / ".claude" / "skills" / "video-use"
        blocked.mkdir(parents=True)
        (blocked / "keep.txt").write_text("keep")
        proc = _run(self.home, self.target)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("not a symlink", proc.stderr)
        self.assertFalse(blocked.is_symlink())
        self.assertEqual((blocked / "keep.txt").read_text(), "keep")
        style = self.target / ".claude" / "skills" / "style-explainer"
        self.assertTrue(style.is_symlink())
        removed = _run(self.home, self.target, "--remove")
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual((blocked / "keep.txt").read_text(), "keep")

    def test_git_repo_gets_a_hint_and_an_untouched_gitignore(self):
        subprocess.run(["git", "init"], cwd=self.target, check=True, capture_output=True, text=True)
        ignore = self.target / ".gitignore"
        ignore.write_text("keep-me\n")
        proc = _run(self.home, self.target)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(".gitignore", proc.stdout)
        self.assertIn(".claude/skills/video-use", proc.stdout)
        self.assertIn(".agents/skills/style-explainer", proc.stdout)
        self.assertEqual(ignore.read_text(), "keep-me\n")

    def test_help_and_unknown_flag(self):
        help_proc = _run(self.home, self.target, "--help")
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("--global", help_proc.stdout)
        self.assertIn("VIDEO_USE_HOME", help_proc.stdout)
        self.assertFalse((self.target / ".claude").exists())
        bad = _run(self.home, self.target, "--nope")
        self.assertEqual(bad.returncode, 2)
        self.assertFalse((self.target / ".claude").exists())

    def test_install_cmd_and_hidden_key(self):
        proc = _run(self.home, self.target, "--install-cmd", extra={"SHELL": "/bin/zsh"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        command = self.home / ".local" / "bin" / "video-use-init"
        self.assertTrue(command.is_symlink())
        self.assertEqual(command.resolve(), INIT.resolve())
        self.assertIn(".zshrc", proc.stdout)
        self.assertIn("not on PATH", proc.stderr)
        self.assertNotIn("SENTINEL_SECRET_VALUE", proc.stdout + proc.stderr)

        repo = Path(self.tmp.name) / "repo"
        (repo / "skills" / "style-explainer").mkdir(parents=True)
        (repo / "SKILL.md").write_text("core\n")
        (repo / "skills" / "style-explainer" / "SKILL.md").write_text("style\n")
        (repo / "scripts").mkdir()
        (repo / "scripts" / "init.sh").write_text("#!/bin/sh\n")
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        secret = repo / ".env"
        secret.write_text("OTHER=1\nELEVENLABS_API_KEY=SENTINEL_SECRET_VALUE\n")
        os.chmod(secret, stat.S_IRUSR | stat.S_IWUSR)
        before = secret.read_text()
        hidden = _run(self.home, self.target, extra={"VIDEO_USE_HOME": str(repo)})
        self.assertEqual(hidden.returncode, 0, hidden.stderr)
        self.assertNotIn("SENTINEL_SECRET_VALUE", hidden.stdout + hidden.stderr)
        self.assertNotIn("YOUR_KEY", hidden.stdout)
        self.assertEqual(secret.read_text(), before)

        secret.write_text("OTHER=keep\nELEVENLABS_API_KEY=\n")
        hinted = _run(self.home, self.target, extra={"VIDEO_USE_HOME": str(repo)})
        self.assertEqual(hinted.returncode, 0, hinted.stderr)
        self.assertIn("YOUR_KEY", hinted.stdout)
        self.assertIn("chmod 600", hinted.stdout)
        self.assertEqual(secret.read_text(), "OTHER=keep\nELEVENLABS_API_KEY=\n")

    def test_tilde_in_video_use_home_expands(self):
        proc = _run(self.home, self.target, extra={"VIDEO_USE_HOME": "~/missing-video-use"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(str(self.home / "missing-video-use"), proc.stderr)
        self.assertFalse((self.target / ".claude").exists())

    def test_old_python_still_links(self):
        bindir = self.home / "bin"
        bindir.mkdir()
        fake = bindir / "python3"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        proc = _run(
            self.home,
            self.target,
            extra={"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("older than", proc.stderr)
        self.assertTrue((self.target / ".claude" / "skills" / "video-use").is_symlink())


if __name__ == "__main__":
    unittest.main()
