#!/usr/bin/env python3
import os
import shutil
import subprocess
import tempfile
import unittest

class TestMsgpFormatSpecifiers(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for test source files
        self.test_dir = tempfile.mkdtemp()
        
        # Create a sample C file with format specifiers
        self.c_file = os.path.join(self.test_dir, "format_test.c")
        with open(self.c_file, "w", encoding="utf-8") as f:
            f.write('''
#include <stdio.h>
int main() {
    // The string literal contains format specifiers like %s and %d.
    printf("min: %s swap peak: %d", "ignored", 100);
    return 0;
}
''')
        
        # Create a sample Python file with format specifiers
        self.py_file = os.path.join(self.test_dir, "format_test.py")
        with open(self.py_file, "w", encoding="utf-8") as f:
            f.write('''
def show():
    # Using the old-style formatting operator
    print("min: %s swap peak: %f" % ("ignored", 100.0))
    
if __name__ == "__main__":
    show()
''')
        
        # Create a sample JavaScript file with format specifiers
        self.js_file = os.path.join(self.test_dir, "format_test.js")
        with open(self.js_file, "w", encoding="utf-8") as f:
            f.write('''
// In JavaScript, format specifiers are not standard but we include one for testing.
console.log("min: %s swap peak: %d");
''')
        
        # Assume msgp.py is located in the same directory as this test script.
        self.msgp_script = os.path.join(os.path.dirname(__file__), "msgp.py")

    def tearDown(self):
        # Remove the temporary directory and its contents
        shutil.rmtree(self.test_dir)

    def run_msgp(self, message, additional_args=None):
        """Utility method to run msgp.py and capture its output."""
        cmd = [self.msgp_script, message, self.test_dir]
        if additional_args:
            cmd.extend(additional_args)
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout

    def test_c_format_specifiers(self):
        """Test that msgp.py processes format specifiers correctly in a C file."""
        # We search for "swap peak" which should appear after removing format specifiers.
        output = self.run_msgp("Memory: 20.8G (min: 250M peak: 27G swap: 2.7G swap peak: 6.7G)", additional_args=["--score", "1"])
        self.assertIn("printf(", output, msg="C file candidate did not contain 'swap peak'.")
        # output = self.run_msgp("peat peak", additional_args=["--score", "1"])
        # self.assertNotIn("printf(", output, msg="C file candidate did not contain 'peat peak'.")

    def test_python_format_specifiers(self):
        """Test that msgp.py processes format specifiers correctly in a Python file."""
        output = self.run_msgp("Memory: 20.8G (min: 250M peak: 27G swap: 2.7G swap peak: 6.7G)", additional_args=["--score", "1"])
        self.assertIn("print(", output, msg="Python file candidate did not contain 'swap peak'.")

    def test_js_format_specifiers(self):
        """Test that msgp.py processes format specifiers correctly in a JavaScript file."""
        output = self.run_msgp("Memory: 20.8G (min: 250M peak: 27G swap: 2.7G swap peak: 6.7G)", additional_args=["--score", "1"])
        self.assertIn("console.log", output, msg="JavaScript file candidate did not contain 'swap peak'.")

if __name__ == '__main__':
    unittest.main()
