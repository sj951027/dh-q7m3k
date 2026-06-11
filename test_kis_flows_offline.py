# -*- coding: utf-8 -*-
"""
test_kis_flows_offline.py — kis_flows.py 오프라인 검증
======================================================
네트워크 없는 부분만: 응답 파싱(필드 변형·쉼표·결측), 토큰 캐시 판정, 증분 upsert
(신규/재기록·잠정→확정 보정·기존 테이블 무접촉), 유니버스 로드.
KIS 실호출은 사용자 첫 실행 로그로 확인.
사용: python test_kis_flows_offline.py [history.db경로]
"""
import json, shutil, sqlite3, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kis_flows as kf

DB_SRC = Path(sys.argv[1] if len(sys.argv) > 1 else "history.db").resolve()

# [1] parse_rows — 정상/쉼표/부호/대금결측/쓰레기행/대체필드
raw = [
    {'stck_bsop_date': '20260611', 'stck_clpr': '12,345', 'prsn_ntby_qty': '-1,000',
     'frgn_ntby_qty': '+2000', 'orgn_ntby_qty': '500',
     'prsn_ntby_tr_pbmn': '-9,999', 'frgn_ntby_tr_pbmn': '88', 'orgn_ntby_tr_pbmn': ''},
    {'stck_bsop_date': '20260610', 'stck_clpr': '12000', 'prsn_ntby_qty': '0',
     'frgn_ntby_qty': '10', 'orgn_ntby_qty': '-10'},                      # 대금 필드 없음
    {'stck_bsop_date': 'TOTAL', 'frgn_ntby_qty': '1'},                    # 날짜 아님 → 스킵
    {'stck_bsop_date': '20260609', 'frgn_shnu_tr_pbmn': '7',              # 대체 필드명
     'frgn_ntby_qty': '3', 'orgn_ntby_qty': '4'},
]
rows = kf.parse_rows(raw, '20260612_1200')
assert len(rows) == 3 and rows[0]['date'] == '20260611'
assert rows[0]['close'] == 12345.0 and rows[0]['person_net_qty'] == -1000.0
assert rows[0]['foreign_net_qty'] == 2000.0 and rows[0]['inst_net_val'] is None
assert rows[1]['foreign_net_val'] is None                                  # 결측은 NaN/None
assert rows[2]['foreign_net_val'] == 7.0, "대체 필드명 흡수 실패"
print("✅ [1] parse_rows: 쉼표/부호/결측/대체필드/쓰레기행 OK")

# [2] 토큰 캐시 판정 (시간 주입 — 네트워크 0)
tk = Path("_t_token.json")
kf.save_token("ABC", time.time() + 7200, tk)
assert kf.load_cached_token(tk) == "ABC"                                   # 2시간 남음 → 재사용
kf.save_token("OLD", time.time() + 600, tk)
assert kf.load_cached_token(tk) is None                                    # 10분 남음 → 재발급 유도
tk.unlink()
print("✅ [2] 토큰 캐시: 충분히 남으면 재사용, 임박하면 None OK")

# [3] upsert — 신규/재기록, 잠정→확정 보정, 기존 테이블 무접촉
work = Path("_t_flows.db"); shutil.copy(DB_SRC, work)
con = sqlite3.connect(work)
before = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
kf.ensure_table(con)
b1 = kf.parse_rows([{'stck_bsop_date': d, 'stck_clpr': '100', 'prsn_ntby_qty': '1',
                     'frgn_ntby_qty': '5', 'orgn_ntby_qty': '2'} for d in
                    ('20260609', '20260610', '20260611')], 't1')
new, rep = kf.upsert_flows(con, '005930', b1)
assert (new, rep) == (3, 0)
b2 = kf.parse_rows([{'stck_bsop_date': '20260611', 'stck_clpr': '100', 'prsn_ntby_qty': '1',
                     'frgn_ntby_qty': '999', 'orgn_ntby_qty': '2'},      # 잠정→확정 수정
                    {'stck_bsop_date': '20260612', 'stck_clpr': '101', 'prsn_ntby_qty': '0',
                     'frgn_ntby_qty': '7', 'orgn_ntby_qty': '1'}], 't2')
new, rep = kf.upsert_flows(con, '005930', b2)
assert (new, rep) == (1, 1)
v = con.execute("SELECT foreign_net_qty FROM daily_flows WHERE ticker='005930' AND date='20260611'").fetchone()[0]
assert v == 999.0, "REPLACE 보정 실패"
assert con.execute("SELECT COUNT(*) FROM daily_flows").fetchone()[0] == 4   # PK 중복 0
assert kf.upsert_flows(con, '005930', []) == (0, 0)                        # 에러 미저장 경로
for t, n in before.items():
    assert con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == n, f"{t} 변형!"
assert con.execute("PRAGMA quick_check").fetchone()[0] == 'ok'
print("✅ [3] upsert: 신규/재기록 집계 · 잠정→확정 보정 · 기존 6테이블 무접촉 · 무결성 OK")

# [4] 유니버스 로드
rid, tks = kf.load_universe_tickers(work, top=300)
assert rid == '20260611' and len(tks) == 300 and tks[0][0] == '005930'
rid, tks = kf.load_universe_tickers(work)
assert len(tks) == 500
con.close(); work.unlink()
print("✅ [4] 유니버스 로드(최신 run·--top) OK")
print("\n🎉 kis_flows 오프라인 검증 전부 통과 (KIS 실호출은 첫 실행 로그로 확인)")
