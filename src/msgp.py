#!/usr/bin/env python3
import os
import re
import sys
import argparse
import concurrent.futures
import signal

# Handle SIGPIPE so that the script does not error when output is truncated (e.g., piped to head)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# Precompiled regular expressions
TOKENIZE_RE = re.compile(r'\s+|[\w.]+|[^\s\w.]')
C_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"')
PY_STRING_LITERAL_RE = re.compile(
    r'(?:r|u|ur|ru|f|fr|rf)?(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')',
    re.IGNORECASE)
JS_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

HIGHLIGHT_CANDIDATE_RE = re.compile(r'"(?:\\.|[^"\\])*"')
FMT_SPEC_RE = re.compile(r'%[-+0# ]*\d*(?:\.\d+)?[dsf]')
ALPHANUMERIC_RE = re.compile(r'[\w.]+')
SINGLE_PERCENT_S_RE = re.compile(r'%[s]')
F_STRING_PREFIX_RE = re.compile(r'^(?i:f|fr|rf)')
STRING_PREFIX_RE = re.compile(r'^(?i:r|u|ur|ru|f|fr|rf)')

def tokenize(text):
    """Tokenize text into whitespace, alphanumeric (including dot) and punctuation tokens."""
    return TOKENIZE_RE.findall(text)

def extract_c_string_literals(content):
    """Extract string literals from C/C++ source code."""
    literals = []
    for m in C_STRING_LITERAL_RE.finditer(content):
        line = content.count('\n', 0, m.start()) + 1
        # Remove the surrounding quotes
        literal = m.group(0)[1:-1]
        literals.append((line, literal))
    return literals

def extract_py_string_literals(content):
    """Extract string literals from Python source code."""
    literals = []
    for m in PY_STRING_LITERAL_RE.finditer(content):
        raw_literal = m.group(0)
        is_f_string = bool(F_STRING_PREFIX_RE.match(raw_literal))
        # Remove any string prefixes (e.g., r, u, f)
        literal = STRING_PREFIX_RE.sub('', raw_literal)
        if (literal.startswith('"') and literal.endswith('"')) or \
           (literal.startswith("'") and literal.endswith("'")):
            literal = literal[1:-1]
        if is_f_string:
            # For f-strings, remove parts within { ... } (treated as wildcards)
            parts = re.split(r'\{.*?\}', literal)
            literal = ' '.join(parts)
        line = content.count('\n', 0, m.start()) + 1
        literals.append((line, literal))
    return literals

def extract_js_string_literals(content):
    """Extract string literals from JavaScript source code."""
    literals = []
    for m in JS_STRING_LITERAL_RE.finditer(content):
        line = content.count('\n', 0, m.start()) + 1
        s = m.group(0)
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            literal = s[1:-1]
        else:
            literal = s
        literals.append((line, literal))
    return literals

# Map file extensions to the corresponding extractor function
EXTRACTOR_MAP = {
    '.c': extract_c_string_literals,
    '.h': extract_c_string_literals,
    '.cpp': extract_c_string_literals,
    '.cc': extract_c_string_literals,
    '.py': extract_py_string_literals,
    '.js': extract_js_string_literals,
    '.jsx': extract_js_string_literals,
}

def score_candidate(message_tokens, message_tokens_set, candidate_tokens):
    """
    Calculate a score for candidate tokens by comparing with message tokens.
    Format specifiers (e.g., %-06d, %10s) are removed.
    Alphanumeric tokens (letters, digits, and dots) contribute 1 point per character,
    and other tokens (whitespace, punctuation) contribute 0.1 point per character.
    The tokens must appear in the same order as in the message.
    """
    filtered = [token for token in candidate_tokens
                if token in message_tokens_set and not FMT_SPEC_RE.fullmatch(token)]
    if not filtered:
        return 0
    prev_index = -1
    for token in filtered:
        try:
            current_index = message_tokens.index(token, prev_index + 1)
        except ValueError:
            return 0
        if current_index <= prev_index:
            return 0
        prev_index = current_index
    score = 0.0
    for token in filtered:
        if ALPHANUMERIC_RE.fullmatch(token):
            score += len(token)
        else:
            score += len(token) * 0.1
    return score

def process_file(filepath, message_tokens, message_tokens_set):
    """Process a single file and return matching string literal candidates."""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return results

    ext = os.path.splitext(filepath)[1].lower()
    extractor = EXTRACTOR_MAP.get(ext)
    if extractor is None:
        return results

    literals = extractor(content)
    if getattr(args, "debug", False):
        print(f"[DEBUG] Processing file: {filepath} with extractor: {extractor.__name__}, found {len(literals)} literals.")
    for line, literal in literals:
        # Remove format specifiers (e.g., %-06d, %10s)
        clean_literal = FMT_SPEC_RE.sub('', literal)
        cand_tokens = tokenize(clean_literal)
        if not cand_tokens:
            continue
        if len(cand_tokens) == 1 and SINGLE_PERCENT_S_RE.fullmatch(cand_tokens[0]):
            continue
        score_val = score_candidate(message_tokens, message_tokens_set, cand_tokens)
        if getattr(args, "debug", False):
            print(f"[DEBUG] File: {filepath}, Line: {line}, Score: {score_val:.2f}")
        if score_val >= args.score:
            results.append({
                'type': 'string',
                'line': line,
                'content': clean_literal,
                'score': score_val,
                'file': filepath
            })
    return results

def highlight_text(text, tokens):
    """Highlight occurrences of tokens in text using ANSI color codes."""
    for token in tokens:
        if token:
            if ALPHANUMERIC_RE.fullmatch(token):
                pattern = r'\b' + re.escape(token) + r'\b'
            else:
                pattern = re.escape(token)
            text = re.sub(pattern, lambda m: "\033[31m" + m.group(0) + "\033[0m", text)
    return text

def highlight_candidate_in_line(line, candidate_content):
    """
    Highlight the candidate content within a string literal in the given line.
    This function searches for a string literal in the line and, if the cleaned inner content
    matches the candidate content, highlights the inner part.
    """
    def repl(m):
        s = m.group(0)
        inner = s[1:-1]
        cleaned = FMT_SPEC_RE.sub('', inner)
        if cleaned == candidate_content:
            return '"' + "\033[31m" + inner + "\033[0m" + '"'
        else:
            return s
    return HIGHLIGHT_CANDIDATE_RE.sub(repl, line, count=1)

def print_with_context(candidate, context_before, context_after, print_line_numbers, file_lines, use_color, with_filename):
    """
    Print the matching candidate with optional context lines.
    If -H/--with-filename is specified, each matching line is prefixed with the file name.
    """
    match_line_index = candidate['line'] - 1
    start_index = max(0, match_line_index - context_before)
    end_index = min(len(file_lines), match_line_index + context_after + 1)
    for i in range(start_index, end_index):
        line_text = file_lines[i].rstrip()
        if use_color:
            if i == match_line_index and candidate['type'] == 'string':
                line_text = highlight_candidate_in_line(line_text, candidate['content'])
            else:
                line_text = highlight_text(line_text, tokenize(args.message))
        if with_filename:
            if print_line_numbers:
                prefix = f"{candidate['file']}:{i+1}:"
            else:
                prefix = f"{candidate['file']}:"
        elif print_line_numbers:
            prefix = f"{i+1}:"
        else:
            prefix = ""
        marker = " <== match" if i == match_line_index else ""
        print(f"{prefix}{line_text}{marker}")
    # Only print separator if any context options are specified
    if args.A != 0 or args.B != 0 or args.C is not None:
        print("-" * 40)

def main():
    parser = argparse.ArgumentParser(
        description="Extracts candidate string literals from source files that match a given message."
    )
    parser.add_argument("message", help="The target message (e.g., 'main: foo.bar(): error occurred')")
    parser.add_argument("directory", help="The root directory to search recursively")
    parser.add_argument("-n", action="store_true", help="Display line numbers")
    parser.add_argument("-A", type=int, default=0, help="Show N lines after the match")
    parser.add_argument("-B", type=int, default=0, help="Show N lines before the match")
    parser.add_argument("-C", type=int, default=None, help="Show N lines of context before and after the match (overrides -A and -B if not specified)")
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument("--color", action="store_true", help="Force color highlighting on")
    color_group.add_argument("--nocolor", action="store_true", help="Force color highlighting off")
    parser.add_argument("--score", type=float, default=0, help="Minimum score threshold for a candidate")
    parser.add_argument("--sort", action="store_true", help="Sort candidates by score (highest first)")
    parser.add_argument("-H", "--with-filename", action="store_true", help="Display filename on each matching line (suppress candidate summary)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    global args
    args = parser.parse_args()

    if getattr(args, "debug", False):
        print(f"[DEBUG] Arguments: {args}")

    if args.C is not None:
        if args.A == 0:
            args.A = args.C
        if args.B == 0:
            args.B = args.C

    use_color = sys.stdout.isatty()
    if args.color:
        use_color = True
    if args.nocolor:
        use_color = False

    message_tokens = tokenize(args.message)
    if getattr(args, "debug", False):
        print(f"[DEBUG] Tokenized message: {message_tokens}")
    message_tokens_set = set(message_tokens)
    candidates = []
    file_paths = []
    for root, _, files in os.walk(args.directory):
        for file in files:
            if file.endswith(('.c', '.h', '.cpp', '.cc', '.py', '.js', '.jsx')):
                file_paths.append(os.path.join(root, file))
    if getattr(args, "debug", False):
        print(f"[DEBUG] Found {len(file_paths)} candidate files.")

    max_workers = os.cpu_count() or 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {executor.submit(process_file, path, message_tokens, message_tokens_set): path for path in file_paths}
        for future in concurrent.futures.as_completed(future_to_path):
            result = future.result()
            if result:
                candidates.extend(result)

    candidates = [cand for cand in candidates if cand['score'] >= args.score]
    if args.sort:
        candidates.sort(key=lambda x: x['score'], reverse=True)
    if getattr(args, "debug", False):
        print(f"[DEBUG] Total candidates found: {len(candidates)}")

    file_cache = {}
    for cand in candidates:
        if not args.with_filename:
            print(f"File: {cand['file']}  Line: {cand['line']}  Type: {cand['type']}  Score: {cand['score']:.1f}")
        if cand['file'] not in file_cache:
            try:
                with open(cand['file'], 'r', encoding='utf-8', errors='ignore') as f:
                    file_cache[cand['file']] = f.readlines()
            except Exception:
                file_cache[cand['file']] = []
        file_lines = file_cache[cand['file']]
        print_with_context(cand, args.B, args.A, args.n, file_lines, use_color, args.with_filename)

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
