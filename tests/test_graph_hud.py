"""graph_hud.py: the unresolved count must match Obsidian's rules (each fixture case below was a
real miscount), and the generated snippet must never carry commit text unless --log is given.

    python3 -m unittest discover -s tests -p 'test_graph_hud.py' -q
"""
import base64
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "obsidian"))
import graph_hud as g

SENTINEL = "zq-sentinel-commit-7431"


def decoded(css):
    """The CSS plus every embedded SVG, decoded: panels are base64, so a plain search sees nothing."""
    blobs = re.findall(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", css)
    return css + "\n" + "\n".join(base64.b64decode(b).decode("utf-8") for b in blobs)


def git(vault, *args):
    return subprocess.run(
        ["git", "-C", str(vault), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        capture_output=True, text=True, check=True)


class VaultShapeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        v = Path(tmp.name) / "vault"
        (v / ".obsidian").mkdir(parents=True)
        (v / ".obsidian/app.json").write_text(json.dumps({"userIgnoreFilters": ["skip/", "/node_modules/"]}))
        outside = Path(tmp.name) / "elsewhere"
        (outside / "deep").mkdir(parents=True)
        (outside / "deep/target.md").write_text("# Target\n")
        os.symlink(outside, v / "linked")  # Obsidian follows folder symlinks; a naive walk does not
        (v / "skip").mkdir()
        (v / "skip/n.md").write_text("[[excluded-and-broken]]\n")
        (v / "AppBinary").write_text("binary")  # an extensionless file is not a note
        (v / "b.md").write_text("---\naliases:\n  - Alias Only\n---\n")
        (v / "a.md").write_text(
            "[[target]] and [[wrongdir/target]]\n"
            "| cell | [[linked/deep/target\\|t]] |\n"                 # escaped vertical bar in a table
            "`[[in-code]]`\n```\n[[fenced]]\n```\n"                  # code is not a link
            "[[Alias Only]] [[missing one]] [[AppBinary]]\n"         # aliases don't resolve
            "[md](linked/deep/target.md) [gone](gone.md) [ext](https://example.com)\n"
        )
        self.vault = v

    def test_counts_like_obsidian(self):
        notes, links, unresolved = g.vault_shape(self.vault)
        self.assertEqual(notes, 3)       # a, b, linked/deep/target; skip/ is excluded
        self.assertEqual(links, 8)       # six wikilinks and two internal Markdown links; code and URLs don't count
        self.assertEqual(unresolved, 5)  # wrongdir/target, Alias Only, missing one, AppBinary, gone

    def test_filters_are_case_insensitive_prefixes_or_regex(self):
        ignored = g.excluded(["Team/Tasks/", "/node_modules/", "**/*.enc"])
        self.assertTrue(ignored("team/tasks/x/result.md"))
        self.assertTrue(ignored("projects/app/node_modules/pkg/README.md"))
        self.assertFalse(ignored("private/secrets.enc"))  # Obsidian has no globs; this filter matches nothing


class MainTests(unittest.TestCase):
    """main() end to end on a throwaway vault, with every path it reads from $HOME redirected."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        v = self.root / "vault"
        (v / ".obsidian").mkdir(parents=True)
        (v / "one.md").write_text("# One\n[[two]] [[nowhere]]\n")
        (v / "two.md").write_text("# Two\n[[one]]\n")
        self.vault = v
        self.out = v / ".obsidian/snippets/phosphor-graph.css"
        self.ticker = self.root / "ticker.json"  # absent unless a test writes it
        for patcher in (mock.patch.object(g, "TICKER", self.ticker),
                        mock.patch.object(g, "VAULT_FILE", self.root / "no-vault-file"),
                        mock.patch.object(g, "STATIC_MARKER", self.root / "no-static-marker"),
                        # git must not walk up from the temp dir into some enclosing repository
                        mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.root)}),
                        mock.patch("sys.stdout", new_callable=io.StringIO)):
            patcher.start()
            self.addCleanup(patcher.stop)
        os.environ.pop("PHOSPHOR_VAULT", None)
        os.environ.pop("PHOSPHOR_GRAPH_STATIC", None)

    def make_git_vault(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        git(self.vault, "init", "-q")
        git(self.vault, "add", "-A")
        git(self.vault, "commit", "-q", "-m", "notes: " + SENTINEL)

    def run_main(self, *extra):
        g.main([str(self.vault), *extra])
        self.assertTrue(self.out.exists(), "phosphor-graph.css was not written")
        return self.out.read_text()

    # (a)
    def test_writes_snippet_without_commit_text_by_default(self):
        self.make_git_vault()
        css = self.run_main()
        self.assertIn("generated by graph_hud.py — edit the script, not this file", css)
        text = decoded(css)
        self.assertIn("2 notes", text)
        self.assertIn("1 unresolved", text)
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn("VAULT LOG", text)
        self.assertNotIn("git log", css)

    def test_log_flag_shows_the_vaults_commits(self):
        # positive control for the test above: the sentinel is findable when the log is asked for
        self.make_git_vault()
        text = decoded(self.run_main("--log"))
        self.assertIn(SENTINEL, text)
        self.assertIn("VAULT LOG", text)

    # (b)
    def test_log_on_a_vault_outside_git_does_not_crash(self):
        probe = subprocess.run(["git", "-C", str(self.vault), "rev-parse", "--git-dir"],
                               capture_output=True, text=True) if shutil.which("git") else None
        if probe is not None:
            self.assertNotEqual(probe.returncode, 0, "precondition: the temp vault must not be in a git repo")
        self.assertEqual(g.commits(self.vault), [])
        text = decoded(self.run_main("--log"))
        self.assertNotIn("VAULT LOG", text)
        self.assertIn("2 notes", text)

    def test_log_without_git_binary_does_not_crash(self):
        with mock.patch.object(g.subprocess, "run", side_effect=FileNotFoundError("git")):
            self.assertEqual(g.commits(self.vault), [])
            self.run_main("--log")

    # (c)
    def test_missing_ticker_cache_still_renders(self):
        self.assertFalse(self.ticker.exists())
        text = decoded(self.run_main())
        self.assertIn("PHOSPHOR//LATTICE", text)
        self.assertNotIn("TICKER", text)  # no feed, no panel
        self.assertNotIn("◆", text)  # and no market key in the legend
        self.assertNotIn("noise &lt;3%", text)

    def test_ticker_rows_render_and_pinned_rows_are_hot(self):
        self.ticker.write_text(json.dumps({"at": time.time(), "errors": [], "rows": [
            {"symbol": "AAA", "price": 1234.5, "change24": 12.0, "pinned": True},
            {"symbol": "BBB", "price": 0.01234, "change24": -1.2}]}))
        text = decoded(self.run_main())
        self.assertIn("TICKER", text)
        self.assertIn("◆ AAA", text)
        self.assertIn("1,234", text)
        self.assertIn("▲ +12%", text)
        self.assertIn("0.0123", text)
        self.assertNotIn("STALE", text)

    def test_unreadable_or_stale_ticker_is_amber_not_a_crash(self):
        self.ticker.write_text("{not json")
        self.assertIn("feed unreadable", decoded(self.run_main()))
        self.ticker.write_text(json.dumps({"at": time.time() - 7200, "rows": [{"symbol": "AAA", "price": 1}]}))
        self.assertIn("STALE 2h", decoded(self.run_main()))

    def test_writes_only_when_content_changed(self):
        first = g.main([str(self.vault)])
        self.assertEqual(first, self.out)
        self.assertIsNone(g.main([str(self.vault)]))  # identical content: no rewrite
        (self.vault / "three.md").write_text("[[one]]\n")
        self.assertEqual(g.main([str(self.vault)]), self.out)

    def test_static_flag_stops_the_animations(self):
        css = self.run_main("--static")
        self.assertNotIn("lattice-rain 60s linear infinite", css)
        self.assertNotIn("lattice-sweep 11s linear infinite", css)

    def test_vault_from_env_and_from_config_file(self):
        with mock.patch.dict(os.environ, {"PHOSPHOR_VAULT": str(self.vault)}):
            self.assertEqual(g.resolve_vault(), self.vault)
        cfg = self.root / "vault-file"
        cfg.write_text(str(self.vault) + "\n# anything after the first line is ignored\n")
        with mock.patch.object(g, "VAULT_FILE", cfg):
            self.assertEqual(g.resolve_vault(), self.vault)

    def test_no_vault_or_not_a_vault_exits_nonzero(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as no_vault:
                g.main([])
            self.assertNotIn(no_vault.exception.code, (0, None))
            bare = self.root / "bare"
            bare.mkdir()
            with self.assertRaises(SystemExit) as not_vault:
                g.main([str(bare)])
            self.assertNotIn(not_vault.exception.code, (0, None))
            self.assertIn(".obsidian", str(not_vault.exception.code))
        self.assertFalse((bare / ".obsidian").exists())


if __name__ == "__main__":
    unittest.main()
