# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션에서 작성 — research/ 에서 실행하면 경로 자동 해결.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent
_DATA = _REPO.parent / 'dh-q7m3k-data'

"""regime_check.py — IC 하락이 모델 고유 문제인지 시장 국면인지 관측"""
import sys, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(str(_REPO))
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(_HERE))
import leaderboard as lb
from trend_scan import ic_series

def main():
    close, _ = lb.load_ohlcv(); dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl
    ser = {}
    for trk, mid in [('v3','v30'), ('lowvol','lv_b'), ('lowvol','mom_a'), ('wu','wu_a')]:
        tb, sc, _u = lb.TRACKS[trk]
        s = pd.read_sql(f'SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?',
                        con, params=(mid,))
        s['ticker'] = s['ticker'].astype(str)
        ics, _ = ic_series(s, close, N, didx, excl, lb.REG_DATE.get(mid))
        ser[mid] = ics[10]
    # 트랙 간 일별 IC 상관(공통 날짜)
    for a, b in [('v30','lv_b'), ('v30','mom_a'), ('lv_b','mom_a'), ('v30','wu_a')]:
        com = sorted(set(ser[a]) & set(ser[b]))
        if len(com) < 6: print(f'{a}~{b}: n부족'); continue
        x = np.array([ser[a][k] for k in com]); y = np.array([ser[b][k] for k in com])
        print(f'{a}~{b} 일별IC 상관 r={np.corrcoef(x,y)[0,1]:+.3f} (n={len(com)})')
    # KOSPI 시장수익률 vs IC
    mk = pd.read_sql("SELECT series, date, close FROM market_daily",
                     sqlite3.connect(f'file:{_DATA}/ohlcv.db?mode=ro', uri=True))
    print('market series:', mk['series'].unique())
    ks = mk[mk['series'].str.contains('KOSPI', case=False, na=False)].set_index('date')['close'].sort_index()
    if len(ks):
        fwd10 = ks.shift(-10)/ks - 1
        for m in ['v30','lv_b']:
            com = sorted(set(ser[m]) & set(fwd10.dropna().index))
            x = np.array([ser[m][k] for k in com]); y = np.array([fwd10[k] for k in com])
            print(f'{m} IC(h10) ~ KOSPI fwd10 수익률 상관 r={np.corrcoef(x,y)[0,1]:+.3f} (n={len(com)})')
        # 후반 구간 시장 상태
        print('KOSPI 최근 60일:', ks.iloc[-60], '->', ks.iloc[-1], f'({(ks.iloc[-1]/ks.iloc[-60]-1)*100:+.1f}%)')
    con.close()

if __name__ == '__main__':
    main()
