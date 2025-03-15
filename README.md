# msgp

**msgp** is a multi-language source code search tool that extracts and scores string literals from source files. It searches for any message (not only error messages) within your code. Currently, msgp supports C/C++, Python, and JavaScript/JSX files.

## Features

- **Multi-language Support:**  
  - **C/C++:** Scans `.c`, `.h`, `.cpp`, and `.cc` files  
  - **Python:** Scans `.py` files  
  - **JavaScript:** Scans `.js` and `.jsx` files

- **Message Extraction:**  
  Only string literals are evaluated. (File names and function definitions are excluded from scoring.)

- **Scoring Mechanism:**  
  The tool tokenizes both the provided message and each string literal. It computes a score based on token matches (preserving token order) as follows:  
  - Alphanumeric tokens (letters, digits, and periods) contribute 1 point per character.  
  - Whitespace and punctuation tokens contribute 0.1 point per character.  

- **Output Customization:**  
  - Display context lines similar to grep’s `-A`, `-B`, and `-C` options.  
  - Optionally sort matches by score using the `--sort` option.  
  - Optionally display filename and line number prefixes (similar to grep’s `-H` and `-n` options).  
  - Highlight matching tokens with ANSI color codes (automatically enabled when outputting to a terminal).

- **Parallel Processing:**  
  Processes files concurrently using a thread pool based on your system’s logical CPU count, improving search performance over large codebases.

- **Graceful Termination:**  
  If output is piped (e.g., using `head`), msgp handles `BrokenPipeError` gracefully and exits without error.

## Requirements

- Python 3.6 or later (msgp uses only the Python standard library).

## Installation

Download the `msgp` script and make it executable:

```bash
chmod +x msgp
```

You can then run it directly:

```bash
./msgp [options] <message> <directory>
```

## Usage

```bash
./msgp [options] <message> <directory>
```

### Options

- `<message>`  
  The search message (e.g., `"Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)"`).

- `<directory>`  
  The root directory to search recursively for source files.

- `-n`  
  Display line numbers in the output.

- `-A <N>`  
  Show N lines after the matching line.

- `-B <N>`  
  Show N lines before the matching line.

- `-C <N>`  
  Show N lines before and after the matching line (overrides `-A` and `-B` if they are not specified).

- `--score <value>`  
  Only include candidates with a score equal to or above the specified value.

- `--sort`  
  Sort the output candidates by score (highest first).

- `-H` or `--with-filename`  
  Display the filename for each matching line (and omit the summary header).

- `--color`  
  Force color highlighting on.

- `--nocolor`  
  Force color highlighting off.

## Examples

### 1. Basic Search

Search for a message across all supported source files in a directory:

```bash
./msgp "Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)" ~/projects/mycode
```

### 2. Filter by Score

Display only matches with a score of at least 6:

```bash
./msgp --score 6 "Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)" ~/projects/mycode
```

### 3. Show Context Lines

Show 2 lines before and 3 lines after the matching line:

```bash
./msgp -B 2 -A 3 "Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)" ~/projects/mycode
```

Or use symmetric context with `-C`:

```bash
./msgp -C 3 "Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)" ~/projects/mycode
```

### 4. Sorted Output

Sort the results by score (highest scoring matches first):

```bash
./msgp --score 4 --sort "Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)" ~/projects/mycode
```

### 5. Filename Display

Display each matching line with the filename prefixed (like grep’s `-H`), omitting the summary header:

```bash
./msgp -H "Memory: 16G (min: 250M peak: 27G swap: 2.8G swap peak: 6.7G)" ~/projects/mycode
```

## How It Works

1. **Tokenization:**  
   The provided message is split into tokens (whitespace, alphanumeric strings, punctuation) using precompiled regular expressions.

2. **String Extraction:**  
   For each source file (determined by file extension), msgp extracts string literals using language-specific extraction functions.

3. **Scoring:**  
   Each extracted string is "cleaned" by removing format specifiers (e.g., `%-06d`, `%10s`), then tokenized. The script computes a score based on the tokens’ match (and order) relative to the message tokens. Alphanumeric tokens contribute 1 point per character; other tokens contribute 0.1 point per character.

4. **Output:**  
   Matches that meet the score threshold are printed with optional context lines, highlighting, and filename/line prefixes.

5. **Parallel Processing:**  
   Files are processed in parallel using a thread pool sized according to the number of logical CPU cores.

## License

This project is licensed under the **BSD 2-Clause License**.


