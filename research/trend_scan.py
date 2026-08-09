# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션에서 작성 — research/ 에서 실행하면 경로 자동 해결.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent
_DATA = _REPO.parent / 'dh-q7m3k-data'

"""
trend_scan.py — '최근 오르고 있는 모델' 오프라인 탐지 (관측·참고용, 판정 아님)
leaderboard.py 와 동일 프로토콜(ENTRY_LAG=1, 게이트, 날짜×시장 Spearman)로
누적 IC가 아니라 '앵커 거래일별 IC 시계열'을 만들어 추세를 본다.
- 전/후반 분할 diff, 최근 10일 IC, OLS 기울기(부트스트랩 CI)
- stage3 관측 팩터도 동일 방식
주의: §11 판정은 leaderboard.py 결과가 정본. 여기 수치는 전부 관측/가설.
"""
import sys, json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(str(_REPO))
sys.path.insert(0, str(REPO))
import leaderboard as lb

BOOT = 2000

def ic_series(scores, close, N, didx, excl, reg, horizons=(5, 10, 20)):
    """모델(또는 팩터) 점수 → {h: {anchor_date: ic}}, {h: {anchor_date: exc}}"""
    keep = lb.dedupe_by_anchor(scores, didx, excl, reg=reg)
    dates = list(close.index)
    out = {h: {} for h in horizons}
    exc = {h: {} for h in horizons}
    for rid, g in scores.groupby('run_id'):
        rid = str(rid)
        if rid in excl or rid not in keep:
            continue
        t = lb.anchor(rid, didx)
        if t is None:
            continue
        for h in horizons:
            if t + lb.ENTRY_LAG + h >= N:
                continue
            fwd = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
            jump = close.pct_change(fill_method=None).abs()\
                .iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
            fwd = fwd.where(jump <= lb.JUMP_CAP)
            day_ics, day_excs = [], []
            for mk, gm in g.groupby('market'):
                s = gm.set_index('ticker')['score'].astype(float)
                s.index = s.index.astype(str)
                b = fwd.reindex(s.index)
                m = s.notna() & b.notna()
                if m.sum() < lb.MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3:
                    continue
                day_ics.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
                top = s[m].sort_values(ascending=False).head(lb.TOP_EXC).index
                day_excs.append(float(b[m].reindex(top).mean() - b[m].median()))
            ad = dates[t]
            if day_ics:
                out[h][ad] = float(np.mean(day_ics))
            if day_excs:
                exc[h][ad] = float(np.mean(day_excs))
    return out, exc

def boot_mean_ci(a, seed=7):
    a = np.asarray(a, float)
    if len(a) < 2:
        return (None, None)
    rng = np.random.default_rng(seed)
    b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
    return (float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)))

def slope_ci(y, seed=13):
    """날짜 인덱스에 대한 OLS 기울기(일당 IC 변화) + 페어 부트스트랩 CI"""
    y = np.asarray(y, float); n = len(y)
    if n < 6:
        return None, (None, None)
    x = np.arange(n, dtype=float)
    sl = float(np.polyfit(x, y, 1)[0])
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(BOOT):
        i = rng.integers(0, n, n)
        if len(np.unique(x[i])) < 2:
            continue
        bs.append(np.polyfit(x[i], y[i], 1)[0])
    return sl, (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))

def trend_stats(series_by_date):
    d = sorted(series_by_date.items())
    if len(d) < 4:
        return dict(n=len(d))
    dates = [k for k, _ in d]; y = np.array([v for _, v in d], float)
    n = len(y); half = n // 2
    first, second = y[:half], y[half:]
    rec = y[-10:] if n >= 10 else y
    diff = second.mean() - first.mean()
    # 후반-전반 diff 부트스트랩(각 구간 독립 리샘플)
    rng = np.random.default_rng(21)
    bd = [rng.choice(second, len(second)).mean() - rng.choice(first, len(first)).mean()
          for _ in range(BOOT)]
    sl, sci = slope_ci(y)
    return dict(
        n=n, first_date=dates[0], last_date=dates[-1],
        mean=float(y.mean()), ci=boot_mean_ci(y),
        first_half=float(first.mean()), second_half=float(second.mean()),
        half_diff=float(diff), half_diff_ci=(float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))),
        recent10=float(rec.mean()), recent10_ci=boot_mean_ci(rec),
        slope_per_day=sl, slope_ci=sci,
        pos=float((y > 0).mean()),
    )

def main():
    close, _ = lb.load_ohlcv()
    dates = list(close.index); N = len(dates)
    con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
    partial, dbl, didx = lb.build_gates(con, dates)
    excl = partial | dbl

    results = {}
    # 1) 모델 점수
    for trk, (tb, sc, _u) in lb.TRACKS.items():
        for (mid,) in con.execute(f'SELECT DISTINCT model_id FROM {tb}'):
            s = pd.read_sql(f'SELECT run_id, market, ticker, {sc} AS score FROM {tb} WHERE model_id=?',
                            con, params=(mid,))
            s['ticker'] = s['ticker'].astype(str)
            reg = lb.REG_DATE.get(mid)
            ics, excs = ic_series(s, close, N, didx, excl, reg)
            results[f'{trk}:{mid}'] = {
                'kind': 'model', 'reg': reg,
                **{f'h{h}': trend_stats(ics[h]) for h in (5, 10, 20)},
                'exc5': trend_stats(excs[5]), 'exc20': trend_stats(excs[20]),
            }
            print('done model', trk, mid, flush=True)

    # 2) stage3 관측 팩터 (v3 유니버스) — reg는 v30 등록일로 통일(관측 목적)
    FACTORS = ['oversold_score', 'acc_score', 'trend_score', 'supply_score',
               'fundamental_score', 'ocf_score', 'momentum_score', 'smartmoney_score',
               'roe_value', 'catalyst_score', 'vol_1w_vs_1m_ratio', 'realized_vol',
               'drop_acuteness', 'os_streak', 'composite_score', 'final_score']
    cols = [c[1] for c in con.execute('PRAGMA table_info(stage3_final)')]
    for f in FACTORS:
        if f not in cols:
            continue
        s = pd.read_sql(f'SELECT run_id, market, ticker, "{f}" AS score FROM stage3_final', con)
        s['ticker'] = s['ticker'].astype(str)
        s = s.dropna(subset=['score'])
        if s.empty:
            continue
        ics, excs = ic_series(s, close, N, didx, excl, reg='20260606')
        results[f'factor:{f}'] = {
            'kind': 'factor',
            **{f'h{h}': trend_stats(ics[h]) for h in (5, 10, 20)},
            'exc20': trend_stats(excs[20]),
        }
        print('done factor', f, flush=True)

    con.close()
    out = Path(str(_HERE / 'trend_scan.json'))
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print('saved', out)

if __name__ == '__main__':
    main()
