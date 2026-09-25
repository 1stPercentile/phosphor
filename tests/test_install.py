"""The installer's promises, checked in a throwaway $HOME: it adds to your config and
never replaces it, backs up what it edits, runs twice without doubling anything, and
uninstall hands your files back the way they were."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        h = self.home
        for d in (".config/ghostty", ".config/cmux", ".claude", "vault/.obsidian"):
            (h / d).mkdir(parents=True)
        (h / ".zshrc").write_text("export FOO=1\n")
        (h / ".config/ghostty/config").write_text("font-size = 13\n")
        (h / ".config/cmux/cmux.json").write_text(json.dumps({"app": {"confirmQuit": "never"}}))
        self.mine = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        (h / ".claude/settings.json").write_text(json.dumps(self.mine))
        (h / "vault/.obsidian/appearance.json").write_text(json.dumps({"theme": "moonstone"}))
        (h / "vault/note.md").write_text("[[other]]\n")

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args):
        env = dict(os.environ, HOME=str(self.home), PHOSPHOR_SKIP_SYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
        for k in ("PHOSPHOR_CACHE", "PHOSPHOR_CONFIG", "PHOSPHOR_SIDEBAR"):
            env.pop(k, None)
        return subprocess.run(["python3", str(ROOT / "install.py"), *args], env=env,
                              capture_output=True, text=True, timeout=300)

    def settings(self):
        return json.loads((self.home / ".claude/settings.json").read_text())

    def test_install_twice_then_uninstall(self):
        h = self.home
        for _ in range(2):
            r = self.install("--vault", str(h / "vault"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("✗", r.stdout)

        self.assertEqual((h / ".zshrc").read_text().count(">>> phosphor"), 1)
        self.assertEqual((h / ".config/ghostty/config").read_text().count(">>> phosphor"), 1)
        s = self.settings()
        self.assertEqual(s["model"], "opus")
        self.assertEqual([len(s["hooks"][e]) for e in ("Stop", "UserPromptSubmit", "Notification")], [2, 1, 1])
        self.assertIn("statusline.py", s["statusLine"]["command"])
        cmux = json.loads((h / ".config/cmux/cmux.json").read_text())
        self.assertEqual(cmux["app"], {"confirmQuit": "never"})
        self.assertEqual(cmux["activePaneBorderColor"], "#41FF8D")
        self.assertTrue((h / ".config/cmux/sidebars/phosphor.swift").exists())
        self.assertTrue((h / "vault/.obsidian/snippets/phosphor-graph.css").exists())
        self.assertEqual(json.loads((h / "vault/.obsidian/appearance.json").read_text())["cssTheme"], "Phosphor")
        self.assertTrue(list(h.glob(".zshrc.phosphor-bak-*")))

        r = self.install("--uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((h / ".zshrc").read_text(), "export FOO=1\n")
        self.assertEqual((h / ".config/ghostty/config").read_text(), "font-size = 13\n")
        self.assertEqual(self.settings(), self.mine)
        self.assertFalse((h / ".config/cmux/sidebars/phosphor.swift").exists())

    def test_an_existing_status_line_is_kept(self):
        mine = dict(self.mine, statusLine={"type": "command", "command": "my-line"})
        (self.home / ".claude/settings.json").write_text(json.dumps(mine))
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.settings()["statusLine"]["command"], "my-line")

    def test_unparseable_config_is_left_alone(self):
        (self.home / ".config/cmux/cmux.json").write_text('{ // comments\n "app": {} }\n')
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("left alone", r.stdout)
        self.assertEqual((self.home / ".config/cmux/cmux.json").read_text(), '{ // comments\n "app": {} }\n')

    def test_dry_run_changes_nothing(self):
        def files():   # Apple's python keeps its own bytecode cache in ~/Library/Caches
            return {p: p.read_bytes() for p in self.home.rglob("*")
                    if p.is_file() and "Library/Caches" not in str(p)}
        before = files()
        r = self.install("--dry-run", "--vault", str(self.home / "vault"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = files()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
