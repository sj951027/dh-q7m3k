#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checkup.py — 정기 점검 패널 (research 모드, 읽기 전용)

목적: 매주 1회 실행해 세 트랙(v3·lowvol·large 프록시)의 상태를 한 화면에 찍고,
사전 정의된 룰로 '노이즈 / 기움 / 유의 / 기준변화 의심'을 자동 라벨링한다.

세 가지 감시축 (사용자 요청):
  ① IC 안정성   — 점수 적중도가 시간이 가며 무너지나/살아나나 (전반 vs 후반 IC)
  ② 베타 변화   — 절대수익이 시장과 얼마나 붙어 가나 (상관·베타 추세)
  ③ 레짐 신호   — regime_score가 forward를 맞히는 방향이 뒤집히나 (상관 부호)

판정 규칙 (PROJECT_KNOWLEDGE §11 상속, 골대 고정):
  - OOS 거래일 < 40 → 무조건 '노이즈'(기본값). 그 전 어떤 수치도 판정 아님.
  - 40+ 도달 시: 부트스트랩 95% CI가 0 위 + 주별 방향 ≥60% → '유의 후보'.
    경계값(CI가 0 살짝 위, 방향 50~60%)은 '기움'까지만.
  - '기준변화 의심': 감시축 ①②③ 중 하나라도 부호/방향이 직전 점검 대비 뒤집히면 플래그.

읽기 전용: 점수·docs·텔레그램 0-diff. 산출은 research/ 리포트(JSON)만.
네트워크 불필요(history.db만 읽음).
사용: python checkup.py            # 콘솔 패널
      python checkup.py --json     # research/checkup_YYYYMMDD.json 저장(추세 추적용)
      python checkup.py --since 20260606   # 특정일 이후 OOS만(판정용)
"""
import sqlite3, argparse, json, os, sys
from datetime import datetime, timezone, timedelta
import numpy as np, pandas as pd
from scipy.stats import spearmanr

# Windows 콘솔(cp949)에서 한글 라벨이 깨지지 않도록 stdout을 UTF-8로 강제.
# (Python 3.7+; 실패해도 무해하게 통과)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DB = "history.db"
KST = timezone(timedelta(hours=9))
GOAL_DAYS = 40          # §11 판정 최소 거래일
ROLL_HALF_MIN = 6       # 전반/후반 분할 최소 run

# 등록일 (OOS 기준): 각 트랙/모델이 언제부터 forward-only인지
REG_DATE = {
    "v30": "20260606", "v31a": "20260606", "v31b": "20260606",
    "v31c": "20260606", "v31d": "20260606",
    "v31f": "20260622", "v31g": "20260622",
    "lv_a": "20260625", "lv_b": "20260625", "lv_c": "20260625",
    "lv_d": "20260625", "lv_a3": "20260625",
    "mom_a": "20260627",
}

def boot_ci(arr, n=2000, seed=42):
    if len(arr) < 2: return (None, None)
    rng = np.random.default_rng(seed)
    b = [rng.choice(arr, len(arr), replace=True).mean() for _ in range(n)]
    return tuple(np.percentile(b, [2.5, 97.5]))

def load(con):
    uni = pd.read_sql('SELECT market, run_id, ticker, price FROM stage1_oversold', con)
    runs = pd.read_sql('SELECT run_id, market, regime_score FROM runs', con)
    return uni, runs

def active_runs(uni):
    runs_all = sorted(uni.run_id.unique())
    panel = uni.pivot_table(index='ticker', columns='run_id', values='price', aggfunc='first')
    act = [runs_all[0]]
    for i in range(1, len(runs_all)):
        a, b = panel[runs_all[i-1]], panel[runs_all[i]]
        both = a.notna() & b.notna()
        if both.sum() == 0: continue
        if (a[both] == b[both]).mean() < 0.99: act.append(runs_all[i])
    return act

def fwd_returns(uni, act, ridx, h):
    u = uni[uni.run_id.isin(act)].copy(); u['step'] = u.run_id.map(ridx)
    p = u.pivot_table(index=['market','ticker'], columns='step', values='price', aggfunc='first')
    recs = []
    for s in sorted(p.columns):
        if s+h not in p.columns: continue
        ret = (p[s+h]/p[s]-1).dropna().reset_index(); ret.columns = ['market','ticker','ret']
        ret['step'] = s
        ret['exret'] = ret['ret'] - ret.groupby('market')['ret'].transform('mean')
        recs.append(ret)
    if not recs: return pd.DataFrame(columns=['run_id','market','ticker','ret','exret'])
    f = pd.concat(recs, ignore_index=True)
    f['run_id'] = f['step'].map({v:k for k,v in ridx.items()})
    return f[['run_id','market','ticker','ret','exret']]

# ---- 점수 로더: 트랙별 (run,market,ticker,score) 반환 ----
def get_scores(con):
    """모든 트랙의 점수를 model_id로 묶어 반환. v3는 동결 v3_scores, lowvol은 lowvol_scores."""
    out = {}
    v3 = pd.read_sql("SELECT run_id, market, ticker, model_id, final_score_v3 AS score FROM v3_scores", con)
    for mid, g in v3.groupby('model_id'):
        out[mid] = g[['run_id','market','ticker','score']].copy()
    lv = pd.read_sql("SELECT run_id, market, ticker, model_id, lowvol_score AS score FROM lowvol_scores", con)
    for mid, g in lv.groupby('model_id'):
        out[mid] = g[['run_id','market','ticker','score']].copy()
    return out

# ---- ① IC 안정성: 전 기간·전반·후반 IC (무너지나/살아나나) ----
def ic_stability(scores, fwd, h, since=None):
    m = scores.merge(fwd, on=['run_id','market','ticker'], how='inner')
    if since: m = m[m.run_id >= since]
    per_run = []
    for (rid, mkt), g in m.groupby(['run_id','market']):
        gg = g[['score','exret']].dropna()
        if len(gg) < 8: continue
        ic, _ = spearmanr(gg['score'], gg['exret'])
        if not np.isnan(ic): per_run.append((rid, ic))
    if not per_run:
        return dict(ic=None, ci=(None,None), n=0, first=None, second=None, dir_ratio=None)
    per_run.sort()
    ics = np.array([x[1] for x in per_run])
    half = len(ics)//2
    first = ics[:half].mean() if half >= ROLL_HALF_MIN else None
    second = ics[half:].mean() if (len(ics)-half) >= ROLL_HALF_MIN else None
    dir_ratio = (ics > 0).mean()   # 양의 IC 비율 (방향 일관성 프록시)
    return dict(ic=ics.mean(), ci=boot_ci(ics), n=len(ics),
                first=first, second=second, dir_ratio=dir_ratio)

# ---- ② 베타 변화: lv선두/추천 바스켓의 시장 베타·상관 (전반 vs 후반) ----
def beta_track(scores, fwd, ridx, act, q=0.8):
    """점수 상위 q 바스켓의 run별 절대수익 vs 시장수익 → 베타·상관, 전/후반 추세."""
    m = scores.merge(fwd, on=['run_id','market','ticker'], how='inner')
    m = m.dropna(subset=['score'])
    m['rp'] = m.groupby(['run_id','market'])['score'].rank(pct=True)
    top = m[m['rp'] >= q]
    bask = top.groupby('run_id')['ret'].mean().rename('bask')
    mkt = fwd.groupby('run_id')['ret'].mean().rename('mkt')
    t = pd.concat([bask, mkt], axis=1).dropna().sort_index()
    if len(t) < 4: return dict(beta=None, corr=None, n=len(t), beta_first=None, beta_second=None)
    def fit(sub):
        if len(sub) < 3: return None, None
        b, a = np.polyfit(sub['mkt'], sub['bask'], 1)
        c = np.corrcoef(sub['mkt'], sub['bask'])[0,1]
        return b, c
    beta, corr = fit(t)
    half = len(t)//2
    bf, _ = fit(t.iloc[:half]) if half >= 3 else (None, None)
    bs, _ = fit(t.iloc[half:]) if (len(t)-half) >= 3 else (None, None)
    return dict(beta=beta, corr=corr, n=len(t), beta_first=bf, beta_second=bs)

# ---- ③ 레짐 신호: regime_score ↔ forward 수익 상관 (부호 뒤집힘 감시) ----
def regime_signal(scores, fwd, runs, ridx, act, q=0.8):
    reg = runs.groupby('run_id')['regime_score'].mean().rename('reg')
    m = scores.merge(fwd, on=['run_id','market','ticker'], how='inner').dropna(subset=['score'])
    m['rp'] = m.groupby(['run_id','market'])['score'].rank(pct=True)
    top = m[m['rp'] >= q]
    bask = top.groupby('run_id')['ret'].mean().rename('bask')
    t = pd.concat([reg, bask], axis=1).dropna().sort_index()
    if len(t) < 4: return dict(corr=None, n=len(t), corr_first=None, corr_second=None)
    corr = np.corrcoef(t['reg'], t['bask'])[0,1]
    half = len(t)//2
    cf = np.corrcoef(t['reg'].iloc[:half], t['bask'].iloc[:half])[0,1] if half >= 3 else None
    cs = np.corrcoef(t['reg'].iloc[half:], t['bask'].iloc[half:])[0,1] if (len(t)-half) >= 3 else None
    return dict(corr=corr, n=len(t), corr_first=cf, corr_second=cs)

# ---- ④ 집중도 비교: 상위 10% vs 20% 바스켓 롱숏 알파 (lv_a '극단 집중' 추적) ----
def concentration(scores, fwd, h):
    """상위/하위 q 바스켓의 롱숏(상위−하위) 알파를 q=0.10, 0.20 두 cutoff로 비교.
    오프라인 가설: lv_a 상위10% 롱숏 +4.09%p > 20% +3.26%p. OOS서 10%가 진짜 나은지 추적.
    롱숏 = 베타 제거 근사(상위−하위) → 순수 종목선택력. 전부 가설(OOS<40)."""
    m = scores.merge(fwd, on=['run_id','market','ticker'], how='inner').dropna(subset=['score'])
    out = {}
    for q in (0.10, 0.20):
        ls = []
        for (rid, mkt), g in m.groupby(['run_id','market']):
            if len(g) < 15: continue
            rp = g['score'].rank(pct=True)
            longs = g.loc[rp >= 1-q, 'ret']; shorts = g.loc[rp <= q, 'ret']
            if len(longs) < 3 or len(shorts) < 3: continue
            ls.append(longs.mean() - shorts.mean())
        if ls:
            arr = np.array(ls)
            out[f"q{int(q*100)}"] = dict(ls_alpha=arr.mean(), ci=boot_ci(arr), n=len(arr))
        else:
            out[f"q{int(q*100)}"] = dict(ls_alpha=None, ci=(None,None), n=0)
    return out

# ---- 판정 룰 ----
def verdict_ic(stat, oos_days):
    """OOS 거래일과 IC·CI로 노이즈/기움/유의 판정."""
    if stat['n'] == 0 or stat['ic'] is None:
        return "측정불가", "forward 부족"
    if oos_days < GOAL_DAYS:
        return "노이즈", f"OOS {oos_days}일 < {GOAL_DAYS} (판정 전)"
    lo, hi = stat['ci']
    dr = stat['dir_ratio']
    if lo is not None and lo > 0 and dr is not None and dr >= 0.6:
        return "유의 후보", f"CI[{lo:+.3f},{hi:+.3f}] 0위 + 방향 {dr*100:.0f}%"
    if lo is not None and lo > 0:
        return "기움", f"CI 0위지만 방향 {dr*100:.0f}%<60%"
    return "미달", f"CI[{lo:+.3f},{hi:+.3f}] 0 포함 → 챔피언 유지"

def detect_shift(curr, prev):
    """직전 점검(prev) 대비 ①②③ 부호/방향 뒤집힘 감지. prev=None이면 첫 점검."""
    if prev is None:
        return []
    flags = []
    for mid in curr.get('models', {}):
        c = curr['models'][mid]; p = prev.get('models', {}).get(mid)
        if not p: continue
        # ① IC 부호 뒤집힘
        ci_now, ci_old = c['ic'].get('ic'), p['ic'].get('ic')
        if ci_now is not None and ci_old is not None and np.sign(ci_now) != np.sign(ci_old) and abs(ci_now) > 0.02:
            flags.append(f"[{mid}] IC 부호 반전: {ci_old:+.3f} → {ci_now:+.3f}")
        # ② 베타 급변 (0.3 이상)
        b_now, b_old = c['beta'].get('beta'), p['beta'].get('beta')
        if b_now is not None and b_old is not None and abs(b_now - b_old) > 0.3:
            flags.append(f"[{mid}] 베타 급변: {b_old:.2f} → {b_now:.2f}")
        # ③ 레짐 상관 부호 반전
        r_now, r_old = c['regime'].get('corr'), p['regime'].get('corr')
        if r_now is not None and r_old is not None and np.sign(r_now) != np.sign(r_old) and abs(r_now) > 0.2:
            flags.append(f"[{mid}] 레짐상관 부호 반전: {r_old:+.2f} → {r_now:+.2f} (장 성격 전환?)")
    return flags

def oos_count(act, reg_date):
    return sum(1 for r in act if r >= reg_date)

def build_report(con, since=None):
    uni, runs = load(con)
    act = active_runs(uni)
    ridx = {r:i for i,r in enumerate(act)}
    fwd5 = fwd_returns(uni, act, ridx, 5)
    fwd20 = fwd_returns(uni, act, ridx, 20)
    scores = get_scores(con)
    now = datetime.now(KST)
    rep = {"generated_at": now.isoformat(), "n_active_runs": len(act),
           "latest_run": act[-1], "models": {}}
    # 점검 대상 모델 (등록일 있는 것만)
    targets = [m for m in REG_DATE if m in scores]
    for mid in targets:
        sc = scores[mid]
        reg_d = REG_DATE[mid]
        oos_d = oos_count(act, reg_d)
        # 주력 h=20d 우선, 없으면 h=5d
        ic20 = ic_stability(sc, fwd20, 20, since=since)
        ic5 = ic_stability(sc, fwd5, 5, since=since)
        ic_main = ic20 if ic20['n'] > 0 else ic5
        h_used = 20 if ic20['n'] > 0 else 5
        beta = beta_track(sc, fwd5, ridx, act)
        regime = regime_signal(sc, fwd5, runs, ridx, act)
        conc = concentration(sc, fwd5, 5)
        vlabel, vwhy = verdict_ic(ic_main, oos_d)
        rep["models"][mid] = {
            "reg_date": reg_d, "oos_days": oos_d, "h_used": h_used,
            "ic": ic_main, "ic_h5": ic5, "beta": beta, "regime": regime,
            "concentration": conc,
            "verdict": vlabel, "why": vwhy,
        }
    return rep

def fmt(x, p=3):
    return f"{x:+.{p}f}" if isinstance(x,(int,float)) and x is not None else "—"

def print_panel(rep, shifts):
    print("="*78)
    print(f"  정기 점검 패널   생성 {rep['generated_at'][:16]}   활성거래일 {rep['n_active_runs']}  최신 {rep['latest_run']}")
    print("="*78)
    print(f"{'모델':7} {'OOS일':>5} {'판정':10} {'IC(h)':>9} {'CI하한':>8} {'방향%':>6} {'베타':>6} {'레짐상관':>8}")
    print("-"*78)
    order = ['v30','v31a','v31b','v31c','v31d','v31f','v31g','lv_a','lv_a3','lv_b','lv_c','lv_d','mom_a']
    for mid in [m for m in order if m in rep['models']]:
        d = rep['models'][mid]
        ic = d['ic']
        cilo = ic['ci'][0] if ic['ci'][0] is not None else None
        dr = ic['dir_ratio']
        icstr = f"{fmt(ic['ic'])}(h{d['h_used']})" if ic['ic'] is not None else "—"
        print(f"{mid:7} {d['oos_days']:>5} {d['verdict']:10} {icstr:>9} {fmt(cilo):>8} "
              f"{(f'{dr*100:.0f}' if dr is not None else '—'):>6} {fmt(d['beta']['beta'],2):>6} {fmt(d['regime']['corr'],2):>8}")
    print("-"*78)
    # 감시축 추세 (IC 전/후반, 베타 전/후반, 레짐 전/후반)
    print("\n[감시축 추세] (전반→후반: 무너지나/살아나나/뒤집히나)")
    for mid in [m for m in order if m in rep['models']]:
        d = rep['models'][mid]
        parts = []
        i = d['ic']
        if i['first'] is not None and i['second'] is not None:
            parts.append(f"①IC {fmt(i['first'])}→{fmt(i['second'])}")
        b = d['beta']
        if b['beta_first'] is not None and b['beta_second'] is not None:
            parts.append(f"②β {fmt(b['beta_first'],2)}→{fmt(b['beta_second'],2)}")
        r = d['regime']
        if r['corr_first'] is not None and r['corr_second'] is not None:
            parts.append(f"③레짐 {fmt(r['corr_first'],2)}→{fmt(r['corr_second'],2)}")
        if parts:
            print(f"  {mid:7} " + "  ".join(parts))
    # 집중도 비교 (상위 10% vs 20% 롱숏 알파) — lv_a 극단집중 추적
    print("\n[집중도 비교] 상위10% vs 20% 롱숏알파%p (베타뺀 순수선택력, h5, 전부 가설)")
    for mid in [m for m in order if m in rep['models']]:
        c = rep['models'][mid].get('concentration')
        if not c: continue
        q10, q20 = c.get('q10', {}), c.get('q20', {})
        a10, a20 = q10.get('ls_alpha'), q20.get('ls_alpha')
        if a10 is None and a20 is None: continue
        s10 = f"{a10*100:+.2f}(n{q10['n']})" if a10 is not None else "—"
        s20 = f"{a20*100:+.2f}(n{q20['n']})" if a20 is not None else "—"
        better = ""
        if a10 is not None and a20 is not None:
            better = " ★10%우위" if a10 > a20 else " (20%우위)"
        print(f"  {mid:7} 10%: {s10:>14}   20%: {s20:>14}{better}")
    # 기준변화
    print("\n[기준변화 감시]")
    if shifts:
        for f in shifts:
            print(f"  ⚠️ {f}")
    else:
        print("  직전 점검 대비 부호/방향 반전 없음 (또는 첫 점검).")
    print("\n주의: OOS<40 모델은 전부 노이즈(판정 전). 위 수치는 추세 참고이지 판정 아님.")
    print("="*78)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="research/checkup_날짜.json 저장")
    ap.add_argument("--since", type=str, default=None, help="이 날짜 이후 OOS만(판정용)")
    ap.add_argument("--db", type=str, default=DB)
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    rep = build_report(con, since=a.since)
    con.close()
    # 직전 점검 로드(기준변화 비교)
    os.makedirs("research", exist_ok=True)
    prev = None
    hist = sorted([f for f in os.listdir("research") if f.startswith("checkup_") and f.endswith(".json")])
    if hist:
        try:
            with open(os.path.join("research", hist[-1]), encoding="utf-8") as pf:
                prev = json.load(pf)
        except Exception:
            prev = None
    shifts = detect_shift(rep, prev)
    rep["shift_flags"] = shifts
    print_panel(rep, shifts)
    if a.json:
        fn = f"research/checkup_{datetime.now(KST).strftime('%Y%m%d')}.json"
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n저장: {fn}")

if __name__ == "__main__":
    main()
