import json
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

LINE = Path(__file__).resolve().parents[1] / 'claude-code' / 'statusline.py'
ANSI = re.compile(r'\x1b\[[0-9;]*m|\x1b\]8;;[^\x07]*\x07')


def run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    r = subprocess.run([sys.executable, str(LINE)], input=raw, capture_output=True, text=True)
    return r.returncode, ANSI.sub('', r.stdout).splitlines()


SESSION = {
    'model': {'display_name': 'Opus'},
    'effort': {'level': 'high'},
    'workspace': {'current_dir': '/tmp/project'},
    'context_window': {'used_percentage': 42},
    'rate_limits': {'five_hour': {'used_percentage': 80, 'resets_at': time.time() + 7200},
                    'seven_day': {'used_percentage': 12}},
    'cost': {'total_cost_usd': 1.5, 'total_duration_ms': 3_900_000,
             'total_lines_added': 10, 'total_lines_removed': 2},
}


class StatusLine(unittest.TestCase):
    def test_two_lines_what_and_room(self):
        code, lines = run(SESSION)
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 2)
        self.assertIn('Opus', lines[0]); self.assertIn('High', lines[0]); self.assertIn('project', lines[0])
        self.assertIn('+10/-2', lines[0])
        self.assertIn('ctx', lines[1]); self.assertIn('42%', lines[1]); self.assertIn('7d', lines[1])
        self.assertIn('$1.50', lines[1]); self.assertIn('1h05m', lines[1])

    def test_garbage_stdin_still_prints(self):
        code, lines = run('not json')
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 2)

    def test_unspent_window_about_to_reset_says_so(self):
        s = json.loads(json.dumps(SESSION))
        s['rate_limits']['five_hour'] = {'used_percentage': 20, 'resets_at': time.time() + 600}
        self.assertIn('send it', run(s)[1][1])

    def test_no_nag_when_the_window_is_spent(self):
        self.assertNotIn('send it', run(SESSION)[1][1])


if __name__ == '__main__':
    unittest.main()
