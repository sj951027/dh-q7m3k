# -*- coding: utf-8 -*-
"""v32a 배선 0-diff (2026-10-24): 저장소 v3_rescore(현행) vs 후보(v32a 훅)
※ 배선 전 도구 — 배선 뒤(커밋 142077b~)에 재현하려면 A 를 `git show 142077b~1:v3_rescore.py` 사본으로 바꿔 넣을 것(Codex 10/24 점검 ①). — history.db stage3_final 전 run 으로
v30 은 전 run, v31a~g 는 최근 10 run 을 재점수화해 DataFrame 완전 일치 비교 + spec_hash 비교 + v32a 미리보기. 읽기 전용."""
import hashlib, importlib.util, json, sqlite3, sys, time, warnings
import pandas as pd
warnings.filterwarnings("ignore")
CAND = sys.argv[1]
import v3_rescore as A
spec = importlib.util.spec_from_file_location("v3_cand", CAND); B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)
h = lambda sp: hashlib.sha256(json.dumps(sp, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:12]
print("spec_hash 비교:")
for m in A.MODELS: print(f"  {m}: 현행 {h(A.MODELS[m])} · 후보 {h(B.MODELS[m])} · {'같음' if h(A.MODELS[m]) == h(B.MODELS[m]) else '★다름'}")
print(f"  v32a(새): {h(B.MODELS['v32a'])} · RETIRED 같음: {A.RETIRED == B.RETIRED} · v32a RETIRED 아님: {'v32a' not in B.RETIRED}")
con = sqlite3.connect("file:history.db?mode=ro", uri=True); con.execute("PRAGMA query_only=ON")
allruns = pd.read_sql("SELECT * FROM stage3_final", con); con.close()
runs = sorted(allruns.run_id.astype(str).unique()); t0 = time.time()
cells = diff_cells = 0; rows_cmp = 0; bad = []
for mid, rr in (("v30", runs),) + tuple((m, runs[-10:]) for m in A.MODELS if m != "v30"):
    for rid in rr:
        for mkt in ("kospi", "kosdaq"):
            sub = allruns[(allruns.run_id.astype(str) == rid) & (allruns.market == mkt)]
            if sub.empty: continue
            a = A.rescore(sub.copy(), run_id=rid, market=mkt, spec=A.MODELS[mid]); b = B.rescore(sub.copy(), run_id=rid, market=mkt, spec=B.MODELS[mid])
            cells += 1; rows_cmp += len(a)
            try: pd.testing.assert_frame_equal(a, b, check_exact=True)
            except AssertionError as e: diff_cells += 1; bad.append((mid, rid, mkt, str(e)[:200]))
print(f"\n0-diff: 비교 셀 {cells} (v30 {len(runs)} run × 2시장 + v31a~g 최근 10 run) · 행 {rows_cmp:,} · 다른 셀 {diff_cells} · {time.time()-t0:.0f}s")
for x in bad[:5]: print("  ", x)
# v32a 미리보기: 최근 5 run
print("\nv32a 미리보기(최근 5 run): 셀 행 · 거래대금 중앙값(억) · −999 로 빠진 행(그중 원래 하드 제외 아님) · 상위 10 v30 과 겹침")
for rid in runs[-5:]:
    for mkt in ("kospi", "kosdaq"):
        sub = allruns[(allruns.run_id.astype(str) == rid) & (allruns.market == mkt)]
        if sub.empty: continue
        v = B.rescore(sub.copy(), run_id=rid, market=mkt, spec=B.MODELS["v30"]); w = B.rescore(sub.copy(), run_id=rid, market=mkt, spec=B.MODELS["v32a"])
        med = pd.to_numeric(sub["amt_avg_1m_억"], errors="coerce").median()
        out_new = int(((w.final_score_v3 <= -999)).sum() - (v.final_score_v3 <= -999).sum())
        t_v = list(v.sort_values(["final_score_v3", "ticker"], ascending=[False, True]).ticker.head(10)); t_w = list(w.sort_values(["final_score_v3", "ticker"], ascending=[False, True]).ticker.head(10))
        amt_w = pd.to_numeric(w.set_index("ticker").loc[t_w, "amt_avg_1m_억"], errors="coerce")
        print(f"  {rid} {mkt}: 행 {len(sub)} · 중앙값 {med:.1f}억 · 새로 −999 {out_new} · 상위10 겹침 {len(set(t_v) & set(t_w))}/10 · v32a 상위10 거래대금 중앙 {amt_w.median():.1f}억 · 버킷 {w.bucket.value_counts().to_dict()}")
