# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션에서 작성 — research/ 에서 실행하면 경로 자동 해결.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent
_DATA = _REPO.parent / 'dh-q7m3k-data'

"""
factor_backtest.py — 장기(2023-06~2026-08) 가격 패널 팩터 백테스트 (탐색 전용)
- 월간(20거래일 비중첩) 앵커, h=20d, ENTRY_LAG=1, JUMP_CAP=0.32 (프로토콜 동일)
- 시장(KOSPI/KOSDAQ)별 cross-sectional Spearman IC → 평균
- 유니버스: 정지 제외, 종가>=500원, 20일 평균 거래대금 >= 1억
- ⚠️ 생존편향: 현재 상장종목 소급 — 결과 해석 시 명시(상폐 종목 부재)
- walk-forward: train(~2025-06) 팩터 선정 → test(2025-07~) 검증, lowvol 단독과 짝비교
"""
import json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(str(_DATA / 'ohlcv.db'))
OUT = Path(str(_HERE / 'factor_backtest.json'))
H = 20; LAG = 1; JUMP = 0.32; MIN_GROUP = 8
BOOT = 2000
TRAIN_END = '20250630'

def load():
    con = sqlite3.connect(f'file:{DATA}?mode=ro', uri=True)
    px = pd.read_sql('SELECT ticker,date,close,volume,shares,is_suspended,market FROM daily_ohlcv', con)
    ks = pd.read_sql("SELECT date,close FROM market_daily WHERE series='KOSPI'", con).set_index('date')['close'].sort_index()
    con.close()
    piv = lambda c: px.pivot_table(index='date', columns='ticker', values=c, aggfunc='last').sort_index()
    close, vol, shares = piv('close'), piv('volume'), piv('shares')
    susp = piv('is_suspended')
    mkt = px.groupby('ticker')['market'].last()
    return close, vol, shares, susp, mkt, ks

def build_factors(close, vol, shares):
    ret = close.pct_change(fill_method=None)
    tval = close * vol
    aval20 = tval.rolling(20, min_periods=10).mean()
    marcap = close * shares
    F = {}
    F['mom_12_1'] = close.shift(20) / close.shift(250) - 1
    F['mom_6_1']  = close.shift(20) / close.shift(125) - 1
    F['rev_1m']   = -(close / close.shift(20) - 1)          # 반전(음수화: 높을수록 최근 하락)
    F['rev_1w']   = -(close / close.shift(5) - 1)
    F['lowvol20'] = -ret.rolling(20, min_periods=10).std()  # 높을수록 저변동
    F['lowvol60'] = -ret.rolling(60, min_periods=30).std()
    F['size_small'] = -np.log(marcap.where(marcap > 0))     # 높을수록 소형
    F['illiq_amihud'] = (ret.abs() / tval.replace(0, np.nan)).rolling(20, min_periods=10).mean()
    F['turnover_low'] = -(vol / shares).rolling(20, min_periods=10).mean()
    F['high52_prox'] = close / close.rolling(250, min_periods=120).max()   # 52주고 근접
    F['volsurge'] = -(tval.rolling(5, min_periods=3).mean() / aval20)      # 거래대금 급증 역방향(조용한 놈)
    return F, aval20, marcap

def main():
    close, vol, shares, susp, mkt, ks = load()
    dates = list(close.index); N = len(dates)
    F, aval20, marcap = build_factors(close, vol, shares)
    print(f'패널: {N}일 x {close.shape[1]}종목, 팩터 {len(F)}개', flush=True)

    anchors = list(range(260, N - H - LAG - 1, 20))          # 월간 비중첩
    print(f'앵커 {len(anchors)}개: {dates[anchors[0]]} ~ {dates[anchors[-1]]}', flush=True)

    # 유니버스 마스크(앵커별)
    def universe(t):
        c = close.iloc[t]
        ok = (c >= 500) & (aval20.iloc[t] >= 1e8)
        s = susp.iloc[t]
        ok &= ~(s.fillna(0) > 0)
        return ok

    def fwd_ret(t):
        f = close.iloc[t + LAG + H] / close.iloc[t + LAG] - 1
        j = close.pct_change(fill_method=None).abs().iloc[t + LAG + 1:t + LAG + H + 1].max()
        return f.where(j <= JUMP)

    def ic_at(t, fac_row):
        f = fwd_ret(t); u = universe(t)
        day = []
        for g in ['KOSPI', 'KOSDAQ']:
            sel = u & (mkt.reindex(u.index) == g)
            s = fac_row[sel]; b = f[sel]
            m = s.notna() & b.notna()
            if m.sum() < MIN_GROUP:
                continue
            day.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
        return float(np.mean(day)) if day else None

    def boot_ci(a, seed=7):
        a = np.asarray(a, float); rng = np.random.default_rng(seed)
        b = [rng.choice(a, len(a)).mean() for _ in range(BOOT)]
        return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]

    # ---- 1) 팩터별 월간 IC ----
    results = {}
    series = {}
    for name, mat in F.items():
        ics = {}
        for t in anchors:
            v = ic_at(t, mat.iloc[t])
            if v is not None:
                ics[dates[t]] = v
        series[name] = ics
        a = np.array(list(ics.values()))
        tr = np.array([v for d, v in ics.items() if d <= TRAIN_END])
        te = np.array([v for d, v in ics.items() if d > TRAIN_END])
        # 시장 국면 분리(KOSPI 20일 선행수익 부호)
        up, dn = [], []
        for d, v in ics.items():
            if d in ks.index:
                i = ks.index.get_loc(d)
                if i + 20 < len(ks):
                    (up if ks.iloc[i + 20] / ks.iloc[i] - 1 > 0 else dn).append(v)
        results[name] = dict(
            n=len(a), ic=float(a.mean()), ci=boot_ci(a), pos=float((a > 0).mean()),
            train=dict(n=len(tr), ic=float(tr.mean()) if len(tr) else None),
            test=dict(n=len(te), ic=float(te.mean()) if len(te) else None,
                      ci=boot_ci(te) if len(te) > 3 else None),
            up_mkt=float(np.mean(up)) if up else None, dn_mkt=float(np.mean(dn)) if dn else None)
        print(f'{name:14s} n={len(a):2d} IC{a.mean():+.3f} train{results[name]["train"]["ic"]:+.3f} '
              f'test{(results[name]["test"]["ic"] if len(te) else 0):+.3f} pos{(a>0).mean():.0%}', flush=True)

    # ---- 2) walk-forward 조합: train IC 상위 k개 동일가중 랭크합 → test ----
    train_rank = sorted(results, key=lambda k: -abs(results[k]['train']['ic'] or 0))
    combos = {}
    for k in (2, 3, 4):
        top = train_rank[:k]
        signs = {f: np.sign(results[f]['train']['ic']) for f in top}
        name = 'combo' + str(k) + '=' + '+'.join(('-' if signs[f] < 0 else '') + f for f in top)
        ics = {}
        for t in anchors:
            u = universe(t)
            rk = None
            for f in top:
                s = F[f].iloc[t][u]
                r = s.rank(pct=True) * signs[f]
                rk = r if rk is None else rk.add(r, fill_value=np.nan)
            v = ic_at(t, rk.reindex(close.columns))
            if v is not None:
                ics[dates[t]] = v
        combos[name] = ics
        te = np.array([v for d, v in ics.items() if d > TRAIN_END])
        tr = np.array([v for d, v in ics.items() if d <= TRAIN_END])
        results[name] = dict(n=len(ics), ic=float(np.mean(list(ics.values()))),
                             train=dict(n=len(tr), ic=float(tr.mean())),
                             test=dict(n=len(te), ic=float(te.mean()), ci=boot_ci(te) if len(te) > 3 else None),
                             members=top)
        print(f'{name}: train{tr.mean():+.3f} test{te.mean():+.3f} (n_test={len(te)})', flush=True)

    # ---- 3) 짝비교: 각 조합 vs lowvol60 단독 (test 구간, 공통 앵커) ----
    base = series['lowvol60']
    pair = {}
    for cname, ics in combos.items():
        com = [d for d in ics if d in base and d > TRAIN_END]
        if len(com) < 4:
            continue
        diff = np.array([ics[d] - base[d] for d in com])
        pair[cname] = dict(n=len(diff), diff=float(diff.mean()), ci=boot_ci(diff, seed=21),
                           pos=float((diff > 0).mean()))
        print(f'짝비교 {cname} - lowvol60: diff{diff.mean():+.4f} CI{pair[cname]["ci"]} n={len(diff)}', flush=True)

    OUT.write_text(json.dumps(dict(factors=results, paired_vs_lowvol60=pair,
                                   caveat='생존편향(현재 상장종목 소급), 상폐수익 미반영, 월간 비중첩 h20'),
                              ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print('saved', OUT)

if __name__ == '__main__':
    main()
