#!/usr/bin/env python3
import os
import re
import sys
import argparse
import concurrent.futures
import signal

# SIGPIPE の対策（head 等で出力が途中で切断された場合にエラーとならないように）
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# 事前コンパイル済み正規表現パターン
TOKENIZE_RE = re.compile(r'\s+|[\w.]+|[^\s\w.]')
C_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"')
PY_STRING_LITERAL_RE = re.compile(
    r'(?:r|u|ur|ru|f|fr|rf)?(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', re.IGNORECASE)
JS_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

HIGHLIGHT_CANDIDATE_RE = re.compile(r'"(?:\\.|[^"\\])*"')
FMT_SPEC_RE = re.compile(r'%[-+0# ]*\d*(?:\.\d+)?[dsf]')
ALPHANUMERIC_RE = re.compile(r'[\w.]+')
SINGLE_PERCENT_S_RE = re.compile(r'%[s]')
F_STRING_PREFIX_RE = re.compile(r'^(?i:f|fr|rf)')
STRING_PREFIX_RE = re.compile(r'^(?i:r|u|ur|ru|f|fr|rf)')

def tokenize(text):
    return TOKENIZE_RE.findall(text)

def extract_c_string_literals(content):
    literals = []
    for m in C_STRING_LITERAL_RE.finditer(content):
        line = content.count('\n', 0, m.start()) + 1
        literal = m.group(0)[1:-1]  # 両端のクォートを除去
        literals.append((line, literal))
    return literals

def extract_py_string_literals(content):
    literals = []
    for m in PY_STRING_LITERAL_RE.finditer(content):
        raw_literal = m.group(0)
        is_f_string = bool(F_STRING_PREFIX_RE.match(raw_literal))
        literal = STRING_PREFIX_RE.sub('', raw_literal)
        if (literal.startswith('"') and literal.endswith('"')) or (literal.startswith("'") and literal.endswith("'")):
            literal = literal[1:-1]
        if is_f_string:
            parts = re.split(r'\{.*?\}', literal)
            literal = ' '.join(parts)
        line = content.count('\n', 0, m.start()) + 1
        literals.append((line, literal))
    return literals

def extract_js_string_literals(content):
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

# 拡張子に応じた文字列抽出関数の選択
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
    メッセージのトークン（順序付きリスト）と候補トークンから、
    フォーマット指定子（FMT_SPEC_RE）にマッチするものを除外し、
    message_tokens_set を用いて membership を高速にチェックします。
    その上で、候補トークンが message_tokens 内に同じ順序で現れるか確認し、
    英数字・ドットのみなら1文字1点、空白や記号は1文字あたり0.1点でスコアを算出します。
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
    for line, literal in literals:
        clean_literal = FMT_SPEC_RE.sub('', literal)
        cand_tokens = tokenize(clean_literal)
        if not cand_tokens:
            continue
        if len(cand_tokens) == 1 and SINGLE_PERCENT_S_RE.fullmatch(cand_tokens[0]):
            continue
        score_val = score_candidate(message_tokens, message_tokens_set, cand_tokens)
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
    for token in tokens:
        if token:
            if ALPHANUMERIC_RE.fullmatch(token):
                pattern = r'\b' + re.escape(token) + r'\b'
            else:
                pattern = re.escape(token)
            text = re.sub(pattern, lambda m: "\033[31m" + m.group(0) + "\033[0m", text)
    return text

def highlight_candidate_in_line(line, candidate_content):
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
    if args.A != 0 or args.B != 0 or args.C is not None:
        print("-" * 40)

def main():
    parser = argparse.ArgumentParser(
        description="メッセージからソースコード候補（文字列のみ）を抽出するツール"
    )
    parser.add_argument("message", help="メッセージ（例: 'main: foo.bar(): エラー発生'）")
    parser.add_argument("directory", help="ソースコードのルートディレクトリ")
    parser.add_argument("-n", action="store_true", help="行番号を表示")
    parser.add_argument("-A", type=int, default=0, help="マッチ行の後N行を表示")
    parser.add_argument("-B", type=int, default=0, help="マッチ行の前N行を表示")
    parser.add_argument("-C", type=int, default=None, help="マッチ行の前後N行を表示（-A, -B に反映）")
    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument("--color", action="store_true", help="強制的に色付けを有効にする")
    color_group.add_argument("--nocolor", action="store_true", help="強制的に色付けを無効にする")
    parser.add_argument("--score", type=float, default=0, help="score の足切り値。指定したスコア未満の候補は追加しない")
    parser.add_argument("--sort", action="store_true", help="候補をスコアでソートして表示する")
    parser.add_argument("-H", "--with-filename", action="store_true", help="各マッチ行にファイル名を表示する（候補概要は非表示）")
    global args
    args = parser.parse_args()

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
    message_tokens_set = set(message_tokens)
    candidates = []
    file_paths = []
    for root, _, files in os.walk(args.directory):
        for file in files:
            if file.endswith(('.c', '.h', '.cpp', '.cc', '.py', '.js', '.jsx')):
                file_paths.append(os.path.join(root, file))

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
