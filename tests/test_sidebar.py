"""The sidebar is only ever rendered by cmux's interpreter, which fails silently:
a colour it can't resolve renders the default, a `\\n` prints literally, a missing
func renders nothing. These tests bake every mood offline and check the output
against the rules that interpreter actually enforces."""

import io
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TMP = tempfile.mkdtemp(prefix="phosphor-test-")
os.environ["PHOSPHOR_CACHE"] = os.path.join(TMP, "cache")
os.environ["PHOSPHOR_CONFIG"] = os.path.join(TMP, "config")
os.environ["PHOSPHOR_SIDEBAR"] = os.path.join(TMP, "sidebars", "phosphor.swift")
sys.path.insert(0, str(ROOT / "engine"))

import mode  # noqa: E402
import render_sidebar  # noqa: E402
import sky  # noqa: E402
import sprite  # noqa: E402

HEX = r'"#[0-9A-Fa-f]{6}"'


def seed_cache():
    """Fresh cache files, so a bake makes no network call at all."""
    now = time.time()
    sky_dir = os.path.join(TMP, "cache", "sky")
    os.makedirs(sky_dir, exist_ok=True)
    json.dump({"lat": 40.7, "lon": -74.0, "city": "test", "at": now},
              open(os.path.join(sky_dir, "loc.json"), "w"))
    json.dump({"temp": 21.5, "code": 61, "cloud": 80, "precip": 2.0, "is_day": 1,
               "sunrise": [now - 3600], "sunset": [now + 3600], "at": now},
              open(os.path.join(sky_dir, "wx.json"), "w"))
    json.dump({"fng": 22, "fng_word": "extreme fear", "btc_d": 57.3, "mcap_24h": -6.1,
               "funding": 0.01, "new_total": 30, "at": now},
              open(os.path.join(sky_dir, "alpha.json"), "w"))
    json.dump({"at": int(now), "errors": [], "rows": [
        {"symbol": "BTC", "price": 101234.5, "change24": 2.4, "mtd": 812.0, "mtd_pct": 0.8},
        {"symbol": "SOL", "price": 0.00001234, "change24": -7.9, "mtd": None},
        {"symbol": "ETH", "price": 3456.7, "change24": None, "mtd": -12.5, "mtd_pct": -0.4}]},
        open(os.path.join(TMP, "cache", "ticker.json"), "w"))


def defined_funcs(src):
    return set(re.findall(r"^func (\w+)\(", src, re.M))


def colour_args(src):
    """Every argument handed to .foregroundColor / .fill / .background."""
    out = []
    for m in re.finditer(r"\.(?:foregroundColor|fill|background)\(", src):
        i, depth = m.end(), 1
        while depth:
            ch = src[i]
            depth += (ch == "(") - (ch == ")")
            i += 1
        out.append(src[m.end():i - 1].strip())
    return out


def lets_outside_funcs(src):
    """`let` is only proven to work inside a func body."""
    bad, depth, in_func = [], 0, False
    for line in src.splitlines():
        if line.startswith("func "):
            in_func = True
        if re.match(r"\s*let \w+", line) and not in_func:
            bad.append(line.strip())
        depth += line.count("{") - line.count("}")
        if in_func and depth == 0:
            in_func = False
    return bad


class Sidebar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_cache()

    def check(self, src):
        funcs = defined_funcs(src)
        for arg in colour_args(src):
            ok = (re.fullmatch(HEX, arg)
                  or re.fullmatch(r"(\w+)\(.*\)", arg) and re.match(r"\w+", arg).group(0) in funcs
                  or re.fullmatch(rf".+\?\s*{HEX}\s*:\s*{HEX}", arg))
            self.assertTrue(ok, f"colour the interpreter can't resolve: {arg!r}")
        for called in set(re.findall(r"\b(pip\w+|sky\w+|hue)\(", src)):
            self.assertIn(called, funcs, f"called but never defined: {called}")
        self.assertEqual(lets_outside_funcs(src), [])
        for text in re.findall(r'Text\("((?:[^"\\]|\\.)*)"\)', src):
            self.assertNotIn("\\n", text, "the interpreter prints \\n literally")
        self.assertEqual(src.count("{"), src.count("}"))
        self.assertEqual(src.count("("), src.count(")"))
        self.assertNotIn("onTapGesture", src, "Phosphor's sidebar is not interactive")

    def test_every_mood_bakes_clean(self):
        for name in list(sprite.POSES) + list(sprite.BY_NAME):
            with self.subTest(mood=name):
                body = render_sidebar.bake(mood=name)
                self.check(body)
                caption = (sprite.POSES.get(name) or sprite.BY_NAME[name])["caption"]
                self.assertTrue(f'return "{caption}"' in body, f"caption {caption!r} not baked")

    def test_markers_all_replaced_and_board_rendered(self):
        body = render_sidebar.bake()
        self.assertNotIn("{{", body)
        self.assertIn('Text("BTC")', body)
        self.assertIn('Text("101,234")', body)
        self.assertIn("▼7.9%", body)

    def test_empty_feed_says_so(self):
        os.remove(os.path.join(TMP, "cache", "ticker.json"))
        try:
            self.assertIn("no feed yet", render_sidebar.bake())
        finally:
            seed_cache()

    def test_sky_units(self):
        self.assertIn('"22°"', sky.render())
        os.makedirs(os.path.join(TMP, "config"), exist_ok=True)
        with open(os.path.join(TMP, "config", "units"), "w") as fh:
            fh.write("f\n")
        try:
            self.assertIn('"71°"', sky.render())
        finally:
            os.remove(os.path.join(TMP, "config", "units"))

    def test_hook_mode_drives_the_live_pose(self):
        os.makedirs(os.path.join(TMP, "cache", "pip"), exist_ok=True)
        with open(os.path.join(TMP, "cache", "pip", "mode.txt"), "w") as fh:
            fh.write(f"work {int(time.time())}\n")
        try:
            self.assertIn('return "work"\n}', sprite.render())
        finally:
            os.remove(os.path.join(TMP, "cache", "pip", "mode.txt"))
        self.assertIn('return "idle"\n}', sprite.render())

    def test_the_checker_catches_what_the_interpreter_drops(self):
        good = render_sidebar.bake(mood="vibing")
        bad_cases = {
            "let colour": good + '\nlet C = "#41FF8D"\nText("x").foregroundColor(C)',
            "undefined func": good + '\nText(pipNope(clock.second))',
            "literal newline": good + '\nText("a\\nb").foregroundColor("#41FF8D")',
            "tap": good + '\nText("x").onTapGesture { }',
        }
        for name, src in bad_cases.items():
            with self.subTest(case=name):
                with self.assertRaises(AssertionError):
                    self.check(src)

    def test_main_writes_once_and_only_on_change(self):
        out = os.environ["PHOSPHOR_SIDEBAR"]
        self.assertEqual(render_sidebar.main(), 0)
        self.assertTrue(os.path.exists(out))
        self.check(open(out, encoding="utf-8").read())


# Pip's hook mode: one small write per hook, never a re-bake, and a working
# stretch that survives turns ending and long sessions.
T0 = 1_790_000_000


class HookMode(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "pip", "mode.txt")
        self.patch = patch.object(mode, "MODE", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def hook(self, word, at):
        with patch.object(mode.time, "time", return_value=at), \
             patch.object(sys, "argv", ["mode.py", word]), \
             patch.object(sys, "stdin", io.StringIO("{}")), \
             patch("subprocess.run") as run, patch("subprocess.Popen") as popen:
            mode.main()
        self.assertFalse(run.called or popen.called, "a hook must never re-bake the sidebar")

    def hook_mode(self, at):
        with patch.object(sprite.time, "time", return_value=at), \
             patch.object(sprite.paths, "cache", lambda *parts: self.path):
            return sprite.hook_mode()

    def test_prompts_in_one_stretch_keep_when_work_began(self):
        self.hook("work", T0)
        self.hook("idle", T0 + 40)
        self.hook("work", T0 + 100)
        self.assertEqual(mode.read(), ("work", T0, T0 + 100, T0 + 100))
        self.hook("work", T0 + 100 + mode.STRETCH + 1)
        self.assertEqual(mode.read()[1], T0 + 100 + mode.STRETCH + 1)

    def test_a_long_working_session_does_not_decay_while_prompts_keep_coming(self):
        for minute in range(0, 31, 3):
            self.hook("work", T0 + minute * 60)
        self.assertEqual(self.hook_mode(T0 + 31 * 60), ("work", T0))

    def test_decay_counts_from_the_last_hook(self):
        self.hook("work", T0)
        self.assertEqual(self.hook_mode(T0 + 19 * 60)[0], "work")
        self.assertEqual(self.hook_mode(T0 + 20 * 60)[0], "idle")
        self.hook("needs", T0)
        self.assertEqual(self.hook_mode(T0 + 60), ("needs", T0))

    def test_a_turn_ending_holds_work_for_the_stretch(self):
        self.hook("work", T0)
        self.hook("idle", T0 + 30)
        self.assertEqual(self.hook_mode(T0 + 31)[0], "work")
        self.assertEqual(self.hook_mode(T0 + mode.STRETCH + 1)[0], "idle")

    def test_old_two_field_file_and_missing_file(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        Path(self.path).write_text(f"work {T0}\n")
        self.assertEqual(mode.read(), ("work", T0, T0, T0))
        self.assertEqual(self.hook_mode(T0 + 60), ("work", T0))
        Path(self.path).unlink()
        self.assertEqual(mode.read(), ("idle", 0, 0, 0))
        self.assertEqual(self.hook_mode(T0)[0], "idle")


if __name__ == "__main__":
    unittest.main()
