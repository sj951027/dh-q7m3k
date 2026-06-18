# -*- coding: utf-8 -*-
"""
inspect_data.py — dh-q7m3k 데이터 점검 (읽기 전용)

repo 루트(history.db 가 있는 폴더)에 두고 실행:
    python inspect_data.py            # 전체
    python inspect_data.py runs       # 거래일 / OOS / 부분실행
    python inspect_data.py ic         # ic_summary.json (h5/h20 + n)
    python inspect_data.py buckets    # 버킷 분포 추이 (v3_archive)
    python inspect_data.py health     # 최신 run 결측 / 관측팩터 / 인덱스
    python inspect_data.py challenger # 챌린저 격차 (model_compare.json)

읽기만 한다. 점수·DB·산출물은 절대 건드리지 않는다.
필요: pandas (이미 설치돼 있음).
"""
import sys, sqlite3, json, re
from pathlib import Path
import pandas as pd

# Windows 콘솔(cp949)에서도 → ≥ 등이 깨지지 않게
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT          = Path(__file__).resolve().parent
DB            = ROOT / "history.db"
V3_ARCHIVE    = ROOT / "v3_archive"
MODEL_COMPARE = ROOT / "docs" / "model_compare.json"
IC_SUMMARY    = ROOT / "docs" / "ic_summary.json"

CHAMP_RUN  = "20260606"   # 챔피언 v30 도입일 = §11 OOS 기준점
OOS_TARGET = 40           # §11 1차 판정 거래일

# 최신 run 에서 비어 있으면 안 되는 핵심 컬럼
CORE_COLS = ["final_score", "RSI", "oversold_score",
             "foreign_5d_억", "foreign_20d_억", "inst_5d_억", "inst_20d_억",
             "amt_avg_1w_억", "quarterly_yoy_%", "risk_level", "earnings_pattern"]


def _hr(title):
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def section_runs():
    _hr("거래일 / OOS / 부분실행")
    if not DB.exists():
        print("  (history.db 없음)"); return
    con = sqlite3.connect(str(DB))
    piv = pd.read_sql(
        "SELECT run_id, market, COUNT(*) n FROM stage3_final "
        "GROUP BY run_id, market ORDER BY run_id", con)
    con.close()
    t = piv.pivot(index="run_id", columns="market", values="n").fillna(0).astype(int)
    t["합계"] = t.sum(axis=1)
    med = t["합계"].median()
    # 행 수가 중앙값의 30% 미만이면 부분실행 의심
    t["플래그"] = t["합계"].apply(lambda x: "  <- 부분실행 의심(IC 제외)" if x < 0.30 * med else "")

    runs = list(t.index)
    oos  = [r for r in runs if r >= CHAMP_RUN]
    remain = max(0, OOS_TARGET - len(oos))

    print(f"  총 거래일(run): {len(runs)}   (최신 {runs[-1]})")
    print(f"  챔피언 도입({CHAMP_RUN}) 이후 OOS: {len(oos)} / {OOS_TARGET}"
          f"   -> 1차 판정까지 {remain}거래일")
    if remain > 0:
        print("  *** OOS 40 미만 = §11 기본값은 '노이즈'. 모델 우열 결론 금지. ***")
    print(f"\n  행 수 추이 (중앙값 {int(med)}):")
    print(t.to_string())


def section_ic():
    _hr("IC 요약 (ic_summary.json) — h=20d 가 핵심")
    if not IC_SUMMARY.exists():
        print("  (docs/ic_summary.json 없음)"); return
    ic = json.loads(IC_SUMMARY.read_text(encoding="utf-8"))
    print(f"  생성: {ic.get('generated_at')}   n_dates={ic.get('n_dates')}   n_picks={ic.get('n_picks')}")
    h = ic.get("headline", {})
    print(f"  헤드라인: h={h.get('horizon')} IC={h.get('ic')} (n={h.get('n')}) "
          f"[{h.get('verdict')}]  ({h.get('score')})")
    h20_ready = any((f.get("n", {}).get("20") or 0) > 0 for f in ic.get("factors", []))
    print(f"  h=20d 산출 여부: {'O (이제 본게임)' if h20_ready else 'X (아직 null — 주력지표 미산출)'}")
    print(f"\n  {'팩터':<14}{'IC h5':>9}{'n(h5)':>8}{'IC h20':>9}{'n(h20)':>8}")
    print("  " + "-" * 46)
    for f in ic.get("factors", []):
        i5  = f.get("ic", {}).get("5");  n5  = f.get("n", {}).get("5")
        i20 = f.get("ic", {}).get("20"); n20 = f.get("n", {}).get("20")
        s5  = f"{i5:+.3f}" if i5 is not None else "NA"
        s20 = f"{i20:+.3f}" if i20 is not None else "null"
        print(f"  {f.get('label',''):<14}{s5:>9}{str(n5):>8}{s20:>9}{str(n20):>8}")
    print("\n  읽는 법: h=20d 가 §11 주력. null 인 동안 h5 는 약한 보조일 뿐.")


def section_buckets(recent=8):
    _hr("버킷 분포 추이 (v3_archive) — 변화는 '레짐'이지 모델 아님")
    if not V3_ARCHIVE.exists():
        print("  (v3_archive 폴더 없음 — perf 핸드오프에 포함됨)"); return
    rows = []
    for f in sorted(V3_ARCHIVE.glob("v3_*_*.csv")):
        m = re.search(r"v3_(kospi|kosdaq)_(\d{8})\.csv", f.name)
        if not m:
            continue
        df = pd.read_csv(f, dtype={"ticker": str})
        if "bucket" not in df.columns:
            continue
        vc = df["bucket"].value_counts()
        rows.append({"run": m.group(2),
                     "BUY": int(vc.get("BUY", 0)),
                     "WAIT": int(vc.get("WAIT", 0)),
                     "OBSERVE": int(vc.get("OBSERVE", 0)),
                     "WATCH": int(vc.get("WATCH", 0)),
                     "EXCLUDE": int(vc.get("EXCLUDE", 0))})
    if not rows:
        print("  (버킷 컬럼이 든 v3 아카이브 CSV 없음)"); return
    d = pd.DataFrame(rows).groupby("run")[["BUY", "WAIT", "OBSERVE", "WATCH", "EXCLUDE"]].sum()
    d["BUY+WAIT"] = d["BUY"] + d["WAIT"]
    print(f"  (버킷/등급은 DB 가 아니라 v3_archive 에만 있음. 최근 {recent}거래일)")
    print(d.tail(recent).to_string())


def section_health():
    _hr("최신 run 건강 — 결측 / 관측팩터 / 인덱스")
    if not DB.exists():
        print("  (history.db 없음)"); return
    con = sqlite3.connect(str(DB))
    mrt = pd.read_sql("SELECT MAX(run_id) m FROM stage3_final", con).m.iloc[0]
    df  = pd.read_sql(f"SELECT * FROM stage3_final WHERE run_id='{mrt}'", con)
    idx = pd.read_sql("SELECT name FROM sqlite_master WHERE type='index' "
                      "AND tbl_name='stage3_final'", con)
    con.close()
    n = len(df)
    print(f"  최신 run {mrt}  (행 {n})")
    print("\n  [핵심 컬럼 결측]  (소수 결측은 정상, 급증하면 점검)")
    thr = max(5, int(0.01 * n))   # 1% 또는 5행 초과면 경고
    for c in CORE_COLS:
        if c in df.columns:
            miss = int(df[c].isna().sum())
            mark = f"  <- 점검! (>{thr})" if miss > thr else ""
            print(f"    {c:<18} {miss:>5} / {n}{mark}")
    # ocf 는 원래 부분 커버리지라 따로
    if "ocf_to_op_ratio" in df.columns:
        miss = int(df["ocf_to_op_ratio"].isna().sum())
        print(f"    {'ocf_to_op_ratio':<18} {miss:>5} / {n}  (부분 커버리지 정상)")

    print("\n  [관측팩터 채움]  (점수엔 안 들어감 / 승격은 검증 후)")
    def filled(col):
        return int(df[col].notna().sum()) if col in df.columns else "(컬럼없음)"
    print(f"    smartmoney_score  채움 {filled('smartmoney_score')} / {n}")
    print(f"    roe_value         채움 {filled('roe_value')} / {n}")
    if "buyback_cancel_flag" in df.columns:
        bb1 = int((pd.to_numeric(df["buyback_cancel_flag"], errors="coerce") == 1).sum())
        print(f"    buyback_cancel=1  {bb1} 건")
    if "insider_source" in df.columns:
        srcs = df["insider_source"].dropna().astype(str).unique()[:3]
        print(f"    insider_source    {list(srcs)}  (기본 OFF — §4-A)")

    print(f"\n  [인덱스] {idx['name'].tolist()}")
    if "idx_stage3_mrt" not in idx["name"].tolist():
        print("    <- idx_stage3_mrt 없음! catalyst_observe 가 느려질 수 있음")


def section_challenger():
    _hr("챌린저 격차 (model_compare.json) — 작고 흔들리면 노이즈")
    if not MODEL_COMPARE.exists():
        print("  (docs/model_compare.json 없음 — `python compare_models.py` 먼저)"); return
    mc = json.loads(MODEL_COMPARE.read_text(encoding="utf-8"))
    H  = [str(x) for x in mc.get("horizons", [1, 2, 3, 5])]
    models = mc.get("models", {})
    if "v30" not in models:
        print("  (v30 챔피언이 없음)"); return
    champ = models["v30"]["full_universe_IC"]
    hl = H[-1]  # 가장 긴 호라이즌(보통 5)
    print(f"  n_active_runs={mc.get('n_active_runs')}  | 호라이즌={H} (거래일)  | h=20d 는 여기 없음")
    head = f"  {'model':<6}" + "".join(f"{'IC h'+h:>9}" for h in H) + f"{'격차 h'+hl:>10}{'BUY+WAIT%':>11}{'n':>7}"
    print(head)
    print("  " + "-" * (len(head) - 2))
    for mid, v in models.items():
        ic = v["full_universe_IC"]
        gap = ic[hl] - champ[hl]
        bw  = v.get("buy_wait_exret_pct", {}).get(hl)
        bwn = v.get("buy_wait_n", {}).get(hl)
        row = f"  {mid:<6}" + "".join(f"{ic[h]:>9.4f}" for h in H)
        row += f"{gap:>+10.4f}" + (f"{bw:>11.3f}" if bw is not None else f"{'':>11}")
        row += f"{str(bwn):>7}"
        print(row)
    print("\n  읽는 법: '격차'(챌린저 IC − 챔피언 IC)가 갱신마다 출렁이면 노이즈.")
    print("  채택은 h=20d 격차의 부트스트랩 CI>0 + 주별 일관성≥60% + Bonferroni(98.75%) 통과 시만.")
    print("  지금은 셋 다 계산 단계 아님 -> 기본값 '노이즈', 챔피언 v30 유지.")


SECTIONS = {
    "runs": section_runs, "ic": section_ic, "buckets": section_buckets,
    "health": section_health, "challenger": section_challenger,
}


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(f"\n[ dh-q7m3k 데이터 점검 ]  루트: {ROOT}")
    if arg == "all":
        for fn in SECTIONS.values():
            fn()
    elif arg in SECTIONS:
        SECTIONS[arg]()
    else:
        print(f"\n알 수 없는 인자: {arg}\n사용: python inspect_data.py [{'|'.join(SECTIONS)}|all]")
        return
    print()


if __name__ == "__main__":
    main()
