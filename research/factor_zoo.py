# -*- coding: utf-8 -*-
# [경로 이식] Claude 세션에서 작성 — research/ 에서 실행하면 경로 자동 해결.
from pathlib import Path as _P
_HERE = _P(__file__).resolve().parent
_REPO = _HERE.parent
_DATA = _REPO.parent / 'dh-q7m3k-data'

"""
factor_zoo.py — 전 유니버스 × 전 데이터원천 팩터 관측 스캔 (탐색 전용 — §11 판정·점수식 반영 금지)
유니버스: v3(stage3_final) · lv_b · wu_a · large_final
원천: stage3 컬럼(OCF 세부 포함) + short_flows + daily_flows + valuation_daily + 가격파생
프로토콜: leaderboard.py 동일(ENTRY_LAG=1, 게이트, 날짜×시장 Spearman, JUMP_CAP)
주의: 테스트 수가 많아(≈250) 95% CI 이탈 몇 개는 우연. Bonferroni 관점으로만 해석.
"""
import sys, json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(str(_REPO))
DATA = Path(str(_DATA))
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(_HERE))
import leaderboard as lb
from trend_scan import boot_mean_ci

HORIZONS = (5, 10, 20)

def load_px():
    con = sqlite3.connect(f'file:{DATA/"ohlcv.db"}?mode=ro', uri=True)
    px = pd.read_sql('SELECT ticker,date,close,volume FROM daily_ohlcv', con)
    con.close()
    close = px.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').sort_index()
    vol = px.pivot_table(index='date', columns='ticker', values='volume', aggfunc='last').sort_index()
    return close, vol

def build_panels(close, vol):
    """anchor 날짜 기준 point-in-time 패널 팩터(dates×tickers)."""
    con = sqlite3.connect(f'file:{DATA/"ohlcv.db"}?mode=ro', uri=True)
    P = {}
    ret = close.pct_change(fill_method=None)
    tval = (close * vol)                                # 거래대금
    aval20 = tval.rolling(20, min_periods=10).mean()
    P['px_ret5'] = close.pct_change(5)
    P['px_ret20'] = close.pct_change(20)
    P['px_mom60x5'] = close.shift(5) / close.shift(60) - 1   # 60d 모멘텀(최근5 제외)
    P['px_vol20'] = ret.rolling(20, min_periods=10).std()
    P['px_amihud20'] = (ret.abs() / tval.replace(0, np.nan)).rolling(20, min_periods=10).mean()

    sf = pd.read_sql('SELECT ticker,date,short_vol_ratio,credit_bal_rate,loan_chg FROM short_flows WHERE date>=\'20260301\'', con)
    svr = sf.pivot_table(index='date', columns='ticker', values='short_vol_ratio', aggfunc='last').sort_index()
    cbr = sf.pivot_table(index='date', columns='ticker', values='credit_bal_rate', aggfunc='last').sort_index()
    lch = sf.pivot_table(index='date', columns='ticker', values='loan_chg', aggfunc='last').sort_index()
    P['sh_short_ratio5'] = svr.rolling(5, min_periods=3).mean()
    P['sh_credit_rate'] = cbr.ffill(limit=5)
    P['sh_credit_chg20'] = cbr.ffill(limit=5).diff(20)
    P['sh_loan_chg5'] = lch.rolling(5, min_periods=3).sum()

    fl = pd.read_sql('SELECT ticker,date,foreign_net_val,inst_net_val,pension_net_val,trust_net_val,person_net_val FROM daily_flows', con)
    for c, nm in [('foreign_net_val','fl_foreign'), ('inst_net_val','fl_inst'),
                  ('pension_net_val','fl_pension'), ('trust_net_val','fl_trust')]:
        pv = fl.pivot_table(index='date', columns='ticker', values=c, aggfunc='last').sort_index()
        pv = pv.reindex(index=close.index)
        s5 = pv.rolling(5, min_periods=3).sum(); s20 = pv.rolling(20, min_periods=10).sum()
        # 거래대금 정규화(대형주 편향 제거)
        P[nm + '5n'] = s5 / aval20.reindex(index=s5.index)
        P[nm + '20n'] = s20 / aval20.reindex(index=s20.index)

    va = pd.read_sql('SELECT ticker,date,pbr,per,div FROM valuation_daily', con)
    for c, nm in [('pbr','va_bp'), ('per','va_ep')]:
        pv = va.pivot_table(index='date', columns='ticker', values=c, aggfunc='last').sort_index()
        pv = pv.reindex(index=close.index).ffill(limit=5)
        P[nm] = 1.0 / pv.where(pv > 0)                 # 역수(가치)
    dv = va.pivot_table(index='date', columns='ticker', values='div', aggfunc='last').sort_index()
    P['va_div'] = dv.reindex(index=close.index).ffill(limit=5)
    con.close()
    return P

def ic_one(sub, fwd):
    """sub: DataFrame(market, ticker, score) 한 날짜. fwd: Series(ticker)."""
    day = []
    for mk, gm in sub.groupby('market'):
        s = gm.set_index('ticker')['score'].astype(float)
        b = fwd.reindex(s.index)
        m = s.notna() & b.notna()
        if m.sum() < lb.MIN_GROUP or s[m].nunique() < 3 or b[m].nunique() < 3:
            continue
        day.append(np.corrcoef(s[m].rank(), b[m].rank())[0, 1])
    return float(np.mean(day)) if day else None

def trend(dic):
    d = sorted(dic.items())
    y = np.array([v for _, v in d], float); n = len(y)
    if n < 5:
        return None
    half = n // 2
    rng = np.random.default_rng(21)
    bd = [rng.choice(y[half:], n - half).mean() - rng.choice(y[:half], half).mean() for _ in range(1000)]
    return dict(n=n, mean=float(y.mean()), ci=boot_mean_ci(y),
                h1=float(y[:half].mean()), h2=float(y[half:].mean()),
                dci=(float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))),
                rec10=float(y[-10:].mean()), pos=float((y > 0).mean()))

def main():
    close, vol = load_px()
    dates = list(close.index); N = len(dates)
    panels = build_panels(close, vol)
    print('panels ready:', len(panels), flush=True)

    con = sqlite3.connect(f'file:{REPO/"history.db"}?mode=ro', uri=True)
    partial, dbl, didx = lb.build_gates(con, dates); excl = partial | dbl

    # ---- 유니버스(run_id, market, ticker) + stage3 팩터 ----
    S3 = ['ocf_score', 'ocf_to_op_ratio', 'fundamental_score', 'roe_value', 'momentum_score',
          'acc_score', 'trend_score', 'supply_score', 'smartmoney_score', 'oversold_score',
          'realized_vol', 'vol_1w_vs_1m_ratio', 'RSI', 'BB_pct', '"drawdown_52w_high_%"',
          '"return_1m_%"', '"annual_yoy_%"', '"quarterly_yoy_%"', '"foreign_20d_억"',
          '"inst_20d_억"', '"amt_avg_1m_억"', 'ocf_pattern']
    s3 = pd.read_sql(f'SELECT run_id, market, ticker, {", ".join(S3)} FROM stage3_final', con)
    s3['ticker'] = s3['ticker'].astype(str)
    s3['ocf_good'] = (s3['ocf_pattern'] == '현금창출양호').astype(float)
    s3['ocf_trap'] = s3['ocf_pattern'].isin(['밸류트랩의심', '이중적자']).astype(float) * -1
    # 탐색용 결합(in-sample 주의): OCF×ROE, OCF×저변동
    for a, b, nm in [('ocf_score', 'roe_value', 'mix_ocf_roe'),
                     ('ocf_score', 'realized_vol', 'mix_ocf_lowvol')]:
        ra = s3.groupby(['run_id', 'market'])[a].rank(pct=True)
        rb = s3.groupby(['run_id', 'market'])[b].rank(pct=True)
        s3[nm] = ra + (1 - rb if b == 'realized_vol' else rb)

    universes = {}
    universes['v3'] = (s3, '20260606')
    lvb = pd.read_sql("SELECT run_id, market, ticker FROM lowvol_scores WHERE model_id='lv_b'", con)
    lvb['ticker'] = lvb['ticker'].astype(str)
    universes['lv_b'] = (lvb.merge(s3.drop(columns=['market']), on=['run_id', 'ticker'], how='left'), '20260625')
    wua = pd.read_sql("SELECT run_id, market, ticker FROM wu_scores WHERE model_id='wu_a'", con)
    wua['ticker'] = wua['ticker'].astype(str)
    universes['wu_a'] = (wua, '20260702')

    stage3_factors = ['ocf_score', 'ocf_to_op_ratio', 'ocf_good', 'ocf_trap', 'fundamental_score',
                      'roe_value', 'momentum_score', 'acc_score', 'supply_score', 'oversold_score',
                      'realized_vol', 'vol_1w_vs_1m_ratio', 'RSI', 'drawdown_52w_high_%',
                      'annual_yoy_%', 'quarterly_yoy_%', 'foreign_20d_억', 'amt_avg_1m_억',
                      'mix_ocf_roe', 'mix_ocf_lowvol']

    results = []
    fwd_cache = {}
    def fwd(t, h):
        k = (t, h)
        if k not in fwd_cache:
            if t + lb.ENTRY_LAG + h >= N:
                fwd_cache[k] = None
            else:
                f = close.iloc[t + lb.ENTRY_LAG + h] / close.iloc[t + lb.ENTRY_LAG] - 1
                j = close.pct_change(fill_method=None).abs().iloc[t + lb.ENTRY_LAG + 1:t + lb.ENTRY_LAG + h + 1].max()
                fwd_cache[k] = f.where(j <= lb.JUMP_CAP)
        return fwd_cache[k]

    for uname, (uni, reg) in universes.items():
        keep = lb.dedupe_by_anchor(uni, didx, excl, reg=reg)
        runs = [(rid, lb.anchor(rid, didx)) for rid in sorted(keep)]
        cand = list(stage3_factors) if uname != 'wu_a' else []
        cand += ['@' + p for p in panels]              # 패널 팩터
        for fac in cand:
            series = {h: {} for h in HORIZONS}
            for rid, t in runs:
                if t is None:
                    continue
                g = uni[uni['run_id'] == rid]
                if fac.startswith('@'):
                    pn = panels[fac[1:]]
                    if dates[t] not in pn.index:
                        continue
                    row = pn.loc[dates[t]]
                    sub = g[['market', 'ticker']].copy()
                    sub['score'] = row.reindex(g['ticker'].values).values
                else:
                    if fac not in g.columns:
                        continue
                    sub = g[['market', 'ticker', fac]].rename(columns={fac: 'score'})
                if sub['score'].notna().sum() < lb.MIN_GROUP:
                    continue
                for h in HORIZONS:
                    f = fwd(t, h)
                    if f is None:
                        continue
                    ic = ic_one(sub, f)
                    if ic is not None:
                        series[h][dates[t]] = ic
            for h in HORIZONS:
                st = trend(series[h])
                if st:
                    results.append(dict(universe=uname, factor=fac.lstrip('@'), h=h, **st))
        print('universe done:', uname, flush=True)

    # ---- 대형 트랙(large_final) — 설계 호라이즌 60~120d 미충족, h20 참고 관측만 ----
    lg = pd.read_sql('SELECT run_id, market, ticker, rim_spread, div_yield, pbr, per, roe_value, '
                     'supply20_net, foreign_20d, inst_20d, annual_yoy, quarterly_yoy, marcap, '
                     'quality_gate, buyback_cancel_flag, is_holding, is_cyclical FROM large_final', con)
    lg['ticker'] = lg['ticker'].astype(str)
    lg['bp'] = 1 / lg['pbr'].where(lg['pbr'] > 0)
    lg['ep'] = 1 / lg['per'].where(lg['per'] > 0)
    lg['supply20_n'] = lg['supply20_net'] / lg['marcap'].where(lg['marcap'] > 0)
    keep = lb.dedupe_by_anchor(lg, didx, excl, reg=None)
    runs = [(rid, lb.anchor(rid, didx)) for rid in sorted(keep)]
    for fac in ['rim_spread', 'div_yield', 'bp', 'ep', 'roe_value', 'supply20_n',
                'foreign_20d', 'inst_20d', 'annual_yoy', 'quarterly_yoy',
                'quality_gate', 'buyback_cancel_flag', 'is_holding', 'is_cyclical']:
        series = {h: {} for h in (10, 20)}
        for rid, t in runs:
            if t is None:
                continue
            g = lg[lg['run_id'] == rid]
            sub = g[['market', 'ticker', fac]].rename(columns={fac: 'score'})
            sub = sub.assign(market='LARGE')           # 단일 그룹(대형 통합)
            for h in (10, 20):
                f = fwd(t, h)
                if f is None:
                    continue
                ic = ic_one(sub, f)
                if ic is not None:
                    series[h][dates[t]] = ic
        for h in (10, 20):
            st = trend(series[h])
            if st:
                results.append(dict(universe='large', factor=fac, h=h, **st))
    print('universe done: large', flush=True)
    con.close()

    out = Path(str(_HERE / 'factor_zoo.json'))
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('saved', out, 'tests:', len(results))

if __name__ == '__main__':
    main()
