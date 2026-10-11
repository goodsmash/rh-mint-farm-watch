#!/usr/bin/env python3
"""Guard for the GitHub Pages site. Run before every push:  python tools/check_pages.py
Fails if any <script ...> or </script> appears INSIDE an inline <script> block
(the bug that broke the site on 2026-10-11) or if an inline block won't parse."""
import re, sys, subprocess, pathlib, shutil, tempfile
bad = 0
for f in pathlib.Path('docs').glob('*.html'):
    h = f.read_text(encoding='utf-8')
    for m in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', h, re.S):
        body = m.group(1)
        line = h[:m.start()].count('\n') + 1
        if re.search(r'<script\b', body, re.I):
            print(f'FAIL {f}:{line} - a <script> tag is pasted inside an inline script'); bad += 1
        if shutil.which('node'):
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as t:
                t.write(body)
            r = subprocess.run(['node', '--check', t.name], capture_output=True, text=True)
            if r.returncode:
                print(f'FAIL {f}:{line} - JS syntax error:\n{r.stderr[-400:]}'); bad += 1
    for src in re.findall(r'<script[^>]*\bsrc="([^"]+)"', h):
        if not src.startswith('http') and not (f.parent / src).exists():
            print(f'FAIL {f} - missing script file {src}'); bad += 1
print('OK - pages look sane' if not bad else f'{bad} problem(s)'); sys.exit(1 if bad else 0)
