"""Read-only independent text audit; does not import the migration/check scripts.
Run: python -B -X utf8 research/handoff/code_20261121_direction_audit.py
The Claude opinion and 11/21 worklog body are intentionally never opened.
"""
from pathlib import Path
import re
import subprocess
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]

def rows(text):
    return {m.group(1): line for line in text.splitlines()
            if (m := re.match(r'^\| (K\d+) ', line))}

def fields(line):
    result, current = [], ''
    for i, char in enumerate(line):
        if char == '|' and (i == 0 or line[i-1] != '\\'):
            result.append(current.strip())
            current = ''
        else:
            current += char
    result.append(current.strip())
    return result[1:-1]

def main():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    old_raw = subprocess.check_output(['git', 'show', 'HEAD:KNOWLEDGE.md'], cwd=ROOT)
    old = old_raw.decode('utf-8')
    new_raw = (ROOT/'KNOWLEDGE.md').read_bytes()
    new = new_raw.decode('utf-8')
    before, after = rows(old), rows(new)
    moved, retained, failures = [], [], []
    for kid, src in before.items():
        if int(kid[1:]) > 41:
            continue
        dest = after[kid]
        if fields(dest)[-1] == f'knowledge/{kid}.md':
            moved.append(kid)
            card = (ROOT/f'knowledge/{kid}.md').read_text(encoding='utf-8')
            card_lines = card.splitlines()
            if card_lines.count(src) != 1:
                failures.append(kid+': exact source row occurrence != 1')
            intro = card.partition('## 원문 행')[0]
            for field in fields(src)[2:]:
                if field not in intro:
                    failures.append(kid+': field absent from card front')
            if '--compact' not in sys.argv:
                print(json.dumps(dict(id=kid, index=fields(dest)[2:5],
                                      original=fields(src)[2:5]), ensure_ascii=False))
        else:
            retained.append(kid)
            if src != dest:
                failures.append(kid+': retained row changed')
    if list(before) != list(after):
        failures.append('row id order changed')
    other_row_changes = [k for k in before if k not in moved and before[k] != after[k]]
    where_lines = (ROOT/'WHERE.md').read_text(encoding='utf-8').splitlines()
    direct_rows = [line for line in where_lines if any(line.startswith('| '+name) for name in
                   ('모델 판정', 'v30·과매도', '저변동 목록', '대형 가치'))]
    where_ids = set(re.findall(r'K\d{2}', '\n'.join(direct_rows)))
    derived_keep = {k for k, line in before.items() if int(k[1:]) <= 41 and
                    (k in where_ids or k == 'K20' or any(w in line for w in ('v32a','ls_t1','lv_e')))}
    assert derived_keep == set(retained), (derived_keep, retained)
    sizes = {name: (ROOT/name).stat().st_size for name in ['KNOWLEDGE.md','DECISIONS.md','PITFALLS.md']}
    print('AUDIT', json.dumps(dict(head=head,old_bytes=len(old_raw),sizes=sizes,moved=moved,
          retained=retained, failures=failures, other_row_changes=other_row_changes,
          knowledge_sha256=hashlib.sha256(new_raw).hexdigest()), ensure_ascii=False))
    # One dated README entry = one record (not one hour / one task).
    structural_primary = {'2026-11-21_knowledge_cards_p18.md', '2026-11-15_promises_checklist.md',
                          '2026-11-13_audit_followup.md'}
    # Human-coded primary purpose, not measured working hours; mixed entries remain mixed in discussion.
    counts = {'성적·자료·실행': 0, '기록·구조': 0}
    for line in (ROOT/'worklog/README.md').read_text(encoding='utf-8').splitlines():
        m = re.search(r'\]\((2026-\d\d-\d\d_[^)]+\.md)\)', line)
        if m and '2026-10-22' <= m[1][:10] <= '2026-11-21':
            kind = '기록·구조' if m[1] in structural_primary else '성적·자료·실행'
            counts[kind] += 1
            print('MONTH_RECORD', m[1], kind, '' if '--compact' in sys.argv else line)
    print('PRIMARY_PURPOSE_COUNTS', counts)
    assert len(moved) == 25 and len(retained) == 16 and not failures and not other_row_changes

if __name__ == '__main__':
    main()
