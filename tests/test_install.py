"""Тесты install.py. Запуск: python3 -m unittest discover tests"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.py"
SKILLS = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.proj = Path(self.tmp.name) / "proj"
        self.home.mkdir()
        self.proj.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args):
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        return subprocess.run([sys.executable, str(INSTALL), *args], capture_output=True, text=True, env=env)

    def test_project_install(self):
        r = self.run_install(str(self.proj))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n in SKILLS:
            self.assertTrue((self.proj / ".claude/skills" / n / "SKILL.md").is_file(), n)
            self.assertTrue((self.proj / ".claude/skills" / n / ".flashstart").is_file(), n)
        self.assertTrue((self.proj / "scripts/trace-check.py").is_file())
        self.assertFalse(any(self.proj.rglob(".gitkeep")))

    def test_reinstall_is_idempotent_and_keeps_other_skills(self):
        other = self.proj / ".claude/skills/my-skill"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("mine")
        self.assertEqual(self.run_install(str(self.proj)).returncode, 0)
        self.assertEqual(self.run_install(str(self.proj)).returncode, 0)
        self.assertEqual((other / "SKILL.md").read_text(), "mine")

    def test_refuses_foreign_folder_without_force(self):
        foreign = self.proj / ".claude/skills/fs-frame"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("чужой")
        r = self.run_install(str(self.proj))
        self.assertEqual(r.returncode, 1)
        self.assertEqual((foreign / "SKILL.md").read_text(), "чужой")
        r = self.run_install(str(self.proj), "--force")
        self.assertEqual(r.returncode, 0)
        self.assertNotEqual((foreign / "SKILL.md").read_text(), "чужой")

    def test_dry_run_changes_nothing(self):
        r = self.run_install(str(self.proj), "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(list(self.proj.iterdir()), [])

    def test_uninstall_removes_only_ours(self):
        self.run_install(str(self.proj))
        other = self.proj / ".claude/skills/my-skill"
        other.mkdir(parents=True)
        (self.proj / "docs/fs/h-001").mkdir(parents=True)
        r = self.run_install(str(self.proj), "--uninstall")
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.proj / ".claude/skills/fs").exists())
        self.assertFalse((self.proj / "scripts/trace-check.py").exists())
        self.assertTrue(other.exists())
        self.assertTrue((self.proj / "docs/fs/h-001").exists())

    def test_global_install(self):
        r = self.run_install("--global")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.home / ".claude/skills/fs-frame/SKILL.md").is_file())
        self.assertTrue((self.home / ".claude/skills/fs/trace-check.py").is_file())

    def test_refuses_flashstart_repo_itself(self):
        r = self.run_install(str(ROOT))
        self.assertNotEqual(r.returncode, 0)

    def test_installed_trace_check_runs(self):
        self.run_install(str(self.proj))
        r = subprocess.run([sys.executable, str(self.proj / "scripts/trace-check.py"), str(ROOT / "examples/h-001/docs/fs")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
