#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
import unittest


class TestLineLengthLimit(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.long_literal = "L" * 210
        self.source_file = os.path.join(self.test_dir, "long_line.py")
        with open(self.source_file, "w", encoding="utf-8") as f:
            f.write(f'print("{self.long_literal}")\n')
        self.msgp_script = os.path.join(os.path.dirname(__file__), "msgp.py")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_msgp(self, additional_args=None):
        cmd = [self.msgp_script, self.long_literal, self.test_dir]
        if additional_args:
            cmd.extend(additional_args)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout

    def test_default_limit_omits_long_line(self):
        output = self.run_msgp()
        self.assertNotIn(self.long_literal, output)

    def test_disabling_limit_shows_long_line(self):
        output = self.run_msgp(["--max-line-length", "0"])
        self.assertIn(self.long_literal, output)


if __name__ == "__main__":
    unittest.main()
