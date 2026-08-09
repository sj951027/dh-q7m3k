# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션에서 작성 — research/ 에서 실행하면 경로 자동 해결.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent
_DATA = _REPO.parent / 'dh-q7m3k-data'

"""paired_compare.py — 같은 앵커 거래일 짝지은 모델 간 IC 차이 (관측용, 판정 아님)
공통 날짜에서 diff = IC_A - IC_B, 부트스트랩(날짜 리샘플) CI, 전/후반, 최근10."""
import sys, sqlite3, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(str(_REPO))
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(_HERE))
import leaderboard as lb
from trend_scan import ic_series, boot_mean_ci

PAIRS = [  # (track, A, B) : A가 B보다 나은가
    ('lowvol', 'lv_a3', 'lv_b'), ('lowvol', 'lv_a', 'lv_b'),
    ('lowvol', 'lv_short', 'lv_b'), ('lowvol', 'mom_a', 'lv_b'),
    ('lowvol', 'sm_a', 'lv_b'), ('lowvol', 'mom_a', 'lv_a3'),
    ('wu', 'sv_a', 'wu_a'),
    ('v3', 'v31d', 'v30'), ('v3', 'v31b', 'v30'),
]

def main():
    close, _ = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    cache = {}
    def series(trk, mid):
        if (trk, mid) in cache: return cache[(trk, mid)]
        tb, sc, _u = lb.TRACKS[trk]
        s = pd.read_sql(f'SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?',
                        con, params=(mid,))
        s['ticker'] = s['ticker'].astype(str)
        ics, _ = ic_series(s, close, N, didx, excl, lb.REG_DATE.get(mid))
        cache[(trk, mid)] = ics
        return ics
    for trk, A, B in PAIRS:
        ia, ib = series(trk, A), series(trk, B)
        for h in (5, 10, 20):
            common = sorted(set(ia[h]) & set(ib[h]))
            if len(common) < 5:
                print(f'{trk} {A}-{B} h{h}: 공통 n={len(common)} 부족'); continue
            d = np.array([ia[h][k] - ib[h][k] for k in common])
            ci = boot_mean_ci(d)
            half = len(d)//2
            rec = d[-10:] if len(d) >= 10 else d
            rci = boot_mean_ci(rec, seed=9)
            print(f'{trk} {A}-{B} h{h}: n={len(d)} diff{d.mean():+.4f}[{ci[0]:+.4f},{ci[1]:+.4f}] '
                  f'pos{(d>0).mean():.0%} 전반{d[:half].mean():+.4f}→후반{d[half:].mean():+.4f} '
                  f'최근10 {rec.mean():+.4f}[{rci[0]:+.4f},{rci[1]:+.4f}]')
    con.close()

if __name__ == '__main__':
    main()
