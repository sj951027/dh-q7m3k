"""2026-10-18 커밋 검토 재현. 가짜 자료/메모리 SQLite만, .env·운영DB·네트워크 접근 없음.
실행: python -X utf8 research/handoff/code_20261018_commit_review.py
성공은 결함이 현재 코드에서 재현됐다는 뜻이다.
"""
from pathlib import Path
from datetime import datetime
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
PTW = ROOT.parent / 'Position-Tracker-Web'
sys.path[:0] = [str(PTW), str(ROOT)]
# app.config의 .env 로딩을 실행하지 않는다.
config = types.ModuleType('app.config')
config.DATABASE_URL = 'sqlite:///:memory:'
sys.modules['app.config'] = config
from app.db import Base, User, SessionLocal, engine
from app import cashflows, benchmark, sell_notes
import data_health

Base.metadata.create_all(engine)
db = SessionLocal()
u = User(email='synthetic', password_hash='unused', cash=1000)
db.add(u)
db.commit()
cashflows.seed_from_cash(db, u, '2026-10-01')
cashflows.add_row(db, u, '2026-10-02', 1000, 'withdraw')
# 소비자의 기존 식을 그대로 확인. 실제 거래 대신 가짜 매수/매도 총액 사용.
source = (PTW/'app/main.py').read_text(encoding='utf-8')
assert 'cash = (deposit - buy_sum + sell_sum) if deposit > 0 else 0.0' in source
expected = u.cash - 1000 + 1200
actual = (u.cash - 1000 + 1200) if u.cash > 0 else 0
assert expected == 200 and actual == 0
print('F1: 원금 인출 뒤 남은 이익 현금 200 -> 표시 0')

idx = {'2026-10-01':100, '2026-10-02':120, '2026-10-05':120, '2026-10-06':120}
snaps = [dict(date=d, total_asset=1000, total_eval=0, total_pnl=0,
              realized_total=0, has_deposit=True) for d in idx]
out = benchmark.build_benchmark(snaps, [], idx, idx, flows={}, acct_from='2026-10-05')
month = out['months'][0]
assert month['acct'] == 0 and month['ks'] == 20 and month['n_acct'] == 1 and month['n'] == 3
print('F3: 계좌 1구간 0% vs 지수 3구간 +20% (같은 구간 지수는 0%)')

# 10/2 저녁 스냅샷 후 입금 500. 10/5 스냅샷에 반영. 가격 변화 없음.
ss = [dict(s) for s in snaps[:3]]
ss[2]['total_asset'] = 1500
out = benchmark.build_benchmark(ss, [], idx, idx, flows={'2026-10-02':500}, acct_from='2026-10-01')
rs = [p['r_acct'] for p in out['points']]
assert rs == [None, -33.3333, 50.0]
print('F2: 저녁 기록 뒤 당일 입금 -> 가짜 -33.3333%, +50.0%')

day = datetime(2026, 10, 1)
def trade(i, side, qty):
    return dict(id=i, code='000001', side=side, qty=qty, price=100, traded_at=day)
ts = [trade(1,'buy',10),trade(2,'sell',4),trade(3,'sell',6)]
# update_trade_reason 의 날짜 <= 조건을 그대로 재현.
actual = sell_notes.sell_context([t for t in ts if t['id'] != 2], '000001',4,100,day)
expected = sell_notes.sell_context(ts[:1], '000001',4,100,day)
assert actual['partial'] == 0 and expected['partial'] == 1
print('F4: 같은 날 후속 매도까지 포함해 첫 4주 부분매도를 전량매도로 기록')

base = {'last':'20261016', 'n_last':2600, 'n_hist':[2736]*10}
branches = {key:dict(base) for key,*_ in data_health.BRANCHES}
rows = data_health.assess(branches,'20261016',['20261015','20261016'])
assert next(r for r in rows if r['key']=='flows')['status'] == 'ok'
print('F6: 전체 2736개 중 보충 136종목 수급 정지 -> 수급 상태 ok')
db.close()
engine.dispose()
