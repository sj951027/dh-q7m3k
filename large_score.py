# -*- coding: utf-8 -*-
"""
large_score.py — 대형 가치주 트랙 2단계: v1 관측 팩터 적재 (LARGE_SCORE_DESIGN §11)
====================================================================================
large_universe(1단계)와 당일 valuation CSV·catalyst CSV·stage3_final을 조인해
v1 관측 팩터를 계산하고 새 테이블 large_final 에 적재한다.

★ 점수(final_score류)는 계산하지 않는다 — 전부 '관측'(가중치 0). 추천/표시 없음.
★ 네트워크 0: 이미 로컬에 있는 산출물만 조인 → .bat 직후 바로 실행 가능.
★ v3 테이블은 읽기만 하고(stage3_final) 쓰기는 large_final 한 곳뿐.

v1 팩터 (설계 §4):
  ① RIM 스프레드  : 정당PBR=(ROE−g)/(COE−g), rim_spread=log(정당PBR/PBR) (양수=저평가)
                    ROE≤g 면 정당PBR 무의미 → NaN. 사분면 플래그(ROE>10% & PBR<1).
                    [v1.1 20260610] 1−PBR/정당PBR → log형으로 교체. 단조변환이라 Spearman
                    순위(=IC) 완전 동일하며, ROE≈g 에서 정당PBR→0+ 일 때 비율식이
                    −수천까지 폭주하던 스케일 문제만 제거(실데이터 ρ=1.0 검증).
  ② 주주환원      : div_yield(배당수익률) + buyback_cancel_flag(있는 범위만 — 아래 갭 참고)
  ③ 품질 게이트   : ocf_to_op_ratio ∈ [0.7, 5.0] (설계 §4③ 예시 구간).
  ④ 수급          : v1은 stage3의 foreign_20d/inst_20d 를 '운반'만(리버설은 3단계 KIS).

명시된 데이터 갭 (상상으로 메우지 않음 — 설계 §13):
  - '최근 2년 흑자'(DART NI) 항은 대형 전수 데이터가 없어 v1 게이트에서 보류.
  - buyback_cancel_flag: catalyst_large_{run_id}.csv(전수 스캔, catalyst_large.py)가
    있으면 그걸 우선 사용, 없으면 v3 catalyst CSV 교집합만(구버전 경로). 미확인 종목은
    0이 아니라 NaN — '확인했는데 없음'과 '확인 안 함'을 구분.
  - [v1.2 20260611] 업종 오버레이 추가(apply_sector_overlay): 공유 sector_cache 는
    불변, large_final 안에서만 라벨 보정. 원본은 sector_raw 로 보존.
    ③우선주 미분류→보통주 상속 → ②'금융(은행)'&비금융→'지주'(KSIC64 오라벨)
    → ①is_financial→'금융' → ④미분류&리츠→'리츠'.
  - KRX는 적자기업 EPS/PER 를 0으로 표기 → 음(−) ROE 식별 불가(roe_value=NaN 처리).
  - stage3 유래 컬럼(ocf/수급/YoY)은 해당 종목이 마지막으로 v3 후보였던 run 값
    (stage3_src_run 기록, 반드시 ≤ 대상 run — 포인트-인-타임 §8).

실행:
    python large_score.py                # run_id = large_universe 최신 run
    python large_score.py --dry-run      # 리포트만, DB 미적재
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from large_universe import load_sector_map   # 섹터 캐시 로더 재사용(오버레이 ③ 우선주 상속용)

DB_PATH = Path("history.db")
TABLE = "large_final"

# ---------------- 관측 파라미터 (점수 아님 — 시작값. 변경 시 이 주석에 기록) ----------------
UNIVERSE_N = 300          # 확정된 분석 유니버스(rank≤N). 적재는 universe 전체(상위 500).
RIM_G = 0.01              # 영구성장률 g — 보수 고정(설계 §4①: 0~2%)
RIM_COE = 0.09            # 자기자본비용 — 단순 상수 시작(설계 §4①: 8~10%, 정교화는 v2)
RIM_FAIR_PBR_CAP = 10.0   # 정당PBR 방어적 상한(폭주 클램프 — 설계 §4① 명시)
QUALITY_OCF_LO = 0.7      # 품질 게이트 OCF/영업이익 하한 (설계 §4③ 예시 구간)
QUALITY_OCF_HI = 5.0      #   〃 상한
# 시클리컬 플래그(설계 §5: '반도체·화학·철강·해운 등') → sector_cache 버킷 매핑(관측용)
CYCLICAL_SECTORS = {'반도체·전자부품', '화학', '철강·1차금속', '조선·기타운송'}


# ============================================================
# 로드
# ============================================================
def latest_universe_run(db_path=DB_PATH):
    with sqlite3.connect(db_path) as con:
        rid = con.execute("SELECT MAX(run_id) FROM large_universe").fetchone()[0]
    if not rid:
        raise RuntimeError("large_universe 테이블이 비어 있음 — 먼저 python large_universe.py 실행")
    return str(rid)


def load_universe(run_id, db_path=DB_PATH):
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql(
            "SELECT * FROM large_universe WHERE run_id=? ORDER BY marcap_rank",
            con, params=(str(run_id),))
    if df.empty:
        raise RuntimeError(f"large_universe 에 run_id={run_id} 없음 — large_universe.py 먼저 실행")
    return df


def load_valuation(run_id):
    """valuation_{mkt}_{run_id}.csv (fetch_valuation 산출, 전종목). 없으면 명확히 실패."""
    frames = []
    for mkt in ('kospi', 'kosdaq'):
        p = Path(f"valuation_{mkt}_{run_id}.csv")
        if not p.exists():
            raise RuntimeError(
                f"{p} 없음 — .bat(2.6단계 fetch_valuation) 실행 여부와 --run-id 확인")
        v = pd.read_csv(p, encoding='utf-8-sig')
        v['ticker'] = v['ticker'].astype(str).str.zfill(6)
        frames.append(v)
    v = pd.concat(frames, ignore_index=True).drop_duplicates('ticker')
    v = v.rename(columns={'PBR': 'pbr', 'PER': 'per', 'DIV': 'div_yield',
                          'BPS': 'bps', 'EPS': 'eps'})
    # KRX 표기 규약: 적자/미산출은 0 → 무효(NaN). 단 div_yield=0 은 '무배당'으로 유효.
    for c in ('pbr', 'per', 'bps', 'eps'):
        v[c] = pd.to_numeric(v[c], errors='coerce')
        v.loc[v[c] <= 0, c] = np.nan
    v['div_yield'] = pd.to_numeric(v['div_yield'], errors='coerce')
    return v[['ticker', 'pbr', 'per', 'div_yield', 'bps', 'eps']]


def load_stage3_latest(tickers, target_run, db_path=DB_PATH):
    """각 종목의 '대상 run 이하' 최신 stage3 행에서 ocf/수급/YoY 운반 (PIT: src_run ≤ target)."""
    cols = ('ticker', 'run_id', 'ocf_to_op_ratio',
            '"annual_yoy_%"', '"quarterly_yoy_%"', '"foreign_20d_억"', '"inst_20d_억"')
    out = []
    tickers = list(tickers)
    with sqlite3.connect(db_path) as con:
        for i in range(0, len(tickers), 400):   # SQLite 변수 한도(999) 대비 분할
            chunk = tickers[i:i + 400]
            q = (f"SELECT {', '.join(cols)} FROM stage3_final "
                 f"WHERE run_id <= ? AND ticker IN ({','.join('?' * len(chunk))})")
            out.append(pd.read_sql(q, con, params=[str(target_run)] + chunk))
    s3 = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=[c.strip('"') for c in cols])
    if s3.empty:
        return pd.DataFrame(columns=['ticker', 'stage3_src_run', 'ocf_to_op_ratio',
                                     'annual_yoy', 'quarterly_yoy', 'foreign_20d', 'inst_20d'])
    s3 = (s3.sort_values('run_id').drop_duplicates('ticker', keep='last')
            .rename(columns={'run_id': 'stage3_src_run',
                             'annual_yoy_%': 'annual_yoy', 'quarterly_yoy_%': 'quarterly_yoy',
                             'foreign_20d_억': 'foreign_20d', 'inst_20d_억': 'inst_20d'}))
    assert (s3['stage3_src_run'].astype(str) <= str(target_run)).all(), "PIT 위반: 미래 run 누출"
    return s3


def load_buyback(run_id):
    """자사주 소각 플래그. 우선순위: catalyst_large(전수) > v3 catalyst(교집합).
    반환: (df, mode) — mode는 'large' | 'v3' | 'none'."""
    p = Path(f"catalyst_large_{run_id}.csv")
    if p.exists():
        c = pd.read_csv(p, encoding='utf-8-sig', dtype={'ticker': str})
        c['ticker'] = c['ticker'].str.zfill(6)
        c['buyback_cancel_flag'] = pd.to_numeric(c['buyback_cancel_flag'], errors='coerce')
        return c[['ticker', 'buyback_cancel_flag', 'buyback_src']].drop_duplicates('ticker'), 'large'
    frames = []
    for mkt in ('kospi', 'kosdaq'):
        q = Path(f"catalyst_{mkt}_{run_id}.csv")
        if q.exists():
            c = pd.read_csv(q, encoding='utf-8-sig')
            c['ticker'] = c['ticker'].astype(str).str.zfill(6)
            frames.append(c[['ticker', 'buyback_cancel_flag']])
    if not frames:
        return pd.DataFrame(columns=['ticker', 'buyback_cancel_flag']), 'none'
    out = pd.concat(frames, ignore_index=True).drop_duplicates('ticker')
    out['buyback_src'] = 'catalyst'
    return out, 'v3' 


# ============================================================
# 업종 오버레이 (순수 — large 전용, 공유 캐시 불변)
# ============================================================
def apply_sector_overlay(df, sector_map=None):
    """large 트랙 전용 업종 라벨 보정. v3가 쓰는 sector_cache.json 은 건드리지 않는다.
    순서 의존: ③ 우선주 상속 → ② KSIC64 지주 보정 → ① 금융 통합 → ④ 리츠.
    (예: 두산우 → ③두산='금융(은행)' 상속 → ②비금융이므로 '지주')"""
    sector_map = sector_map or {}
    out = df.copy()
    out['sector_raw'] = out['sector']
    s = out['sector'].copy()
    m = (s == '미분류') & (out['is_pref'] == 1)                      # ③ 보통주(끝자리 0) 상속
    s.loc[m] = out.loc[m, 'ticker'].map(lambda t: sector_map.get(t[:5] + '0', '미분류'))
    m = (s == '금융(은행)') & (out['is_financial'] == 0)             # ② KSIC64 지주회사 오라벨
    s.loc[m] = '지주'
    s.loc[out['is_financial'] == 1] = '금융'                          # ① 은행·보험·증권 통합(v1)
    m = (s == '미분류') & (out['is_reit'] == 1)                      # ④
    s.loc[m] = '리츠'
    out['sector'] = s
    return out


# ============================================================
# 팩터 계산 (순수 — 오프라인 검증 대상)
# ============================================================
def compute_factors(df):
    """① RIM ② 주주환원 ③ 품질게이트 + 시클리컬 플래그. 행 제외 없음, NaN은 NaN대로."""
    out = df.copy()

    # ROE 근사 = EPS/BPS×100 (자본잠식 BPS≤0, 적자표기 EPS≤0 은 위 로드에서 이미 NaN)
    out['roe_value'] = (out['eps'] / out['bps']) * 100.0

    # ① RIM: 정당PBR = (ROE−g)/(COE−g). ROE≤g → 정당PBR 무의미(NaN).
    roe_frac = out['roe_value'] / 100.0
    fair = (roe_frac - RIM_G) / (RIM_COE - RIM_G)
    fair = fair.where(fair > 0)                       # ROE≤g → NaN
    out['rim_fair_pbr'] = fair.clip(upper=RIM_FAIR_PBR_CAP)
    # log형 스프레드: 양수=정당가 대비 저평가. (구 1−PBR/fair 와 단조 동치 → 순위 불변)
    out['rim_spread'] = np.log(out['rim_fair_pbr'] / out['pbr'])
    quad = (out['roe_value'] > 10.0) & (out['pbr'] < 1.0)
    out['rim_quadrant'] = quad.astype(float)
    out.loc[out['roe_value'].isna() | out['pbr'].isna(), 'rim_quadrant'] = np.nan

    # ③ 품질 게이트: OCF/영업이익 건전 구간(자료 있는 종목만; '2년 흑자' 항은 갭으로 보류)
    ocf = pd.to_numeric(out['ocf_to_op_ratio'], errors='coerce')
    out['quality_gate'] = ((ocf >= QUALITY_OCF_LO) & (ocf <= QUALITY_OCF_HI)).astype(float)
    out.loc[ocf.isna(), 'quality_gate'] = np.nan

    # 시클리컬 플래그(관측 — 페널티 아님)
    out['is_cyclical'] = out['sector'].isin(CYCLICAL_SECTORS).astype(int)
    return out


# ============================================================
# 적재 / 리포트
# ============================================================
FINAL_COLS = [
    'run_id', 'run_timestamp', 'market', 'ticker', 'name',
    'close', 'marcap', 'stocks', 'marcap_rank', 'sector', 'sector_raw',
    'is_pref', 'is_spac', 'is_reit', 'is_holding', 'is_financial', 'is_cyclical',
    'pbr', 'per', 'div_yield', 'bps', 'eps',
    'roe_value', 'rim_fair_pbr', 'rim_spread', 'rim_quadrant',
    'buyback_cancel_flag', 'buyback_src',
    'ocf_to_op_ratio', 'annual_yoy', 'quarterly_yoy', 'quality_gate',
    'foreign_20d', 'inst_20d', 'stage3_src_run',
]


def save_db(df, run_id, db_path=DB_PATH):
    keep = df[FINAL_COLS].copy()
    with sqlite3.connect(db_path) as con:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,))
        if cur.fetchone():
            existing = {r[1] for r in cur.execute(f"PRAGMA table_info({TABLE})")}
            for c in FINAL_COLS:                       # v1.x 컬럼 추가분 자동 마이그레이션
                if c not in existing:
                    cur.execute(f'ALTER TABLE {TABLE} ADD COLUMN "{c}"')
                    print(f"   • 스키마 마이그레이션: {TABLE}.{c} 추가")
            cur.execute(f"DELETE FROM {TABLE} WHERE run_id=?", (str(run_id),))
            con.commit()
        keep.to_sql(TABLE, con, if_exists='append', index=False)
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_large_final_rt ON {TABLE}(run_id, ticker)")
        con.commit()
        n = cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE run_id=?", (str(run_id),)).fetchone()[0]
    print(f"💾 DB 적재: {TABLE} run_id={run_id} {n}행")
    return n


def report(df, run_id):
    u = df[df['marcap_rank'] <= UNIVERSE_N]
    print("\n" + "=" * 64)
    print(f"📋 large_final 관측 리포트 — run {run_id} (유니버스 rank≤{UNIVERSE_N}, n={len(u)})")
    print("   ※ 전부 가중치 0 관측값. 추천·점수 아님(검증은 §9: h=60/120d).")
    print("=" * 64)
    cov = {
        'pbr': u['pbr'].notna().sum(), 'roe_value': u['roe_value'].notna().sum(),
        'rim_spread': u['rim_spread'].notna().sum(),
        'div_yield>0': (u['div_yield'] > 0).sum(),
        'buyback(확인)': u['buyback_cancel_flag'].notna().sum(),
        'ocf(stage3)': u['ocf_to_op_ratio'].notna().sum(),
        'foreign_20d': u['foreign_20d'].notna().sum(),
    }
    print("커버리지: " + ' · '.join(f"{k} {v}/{len(u)}" for k, v in cov.items()))
    q = u['rim_spread'].quantile([0.25, 0.5, 0.75])
    print(f"rim_spread 분포: 25% {q[0.25]:+.2f} / 중앙 {q[0.5]:+.2f} / 75% {q[0.75]:+.2f}"
          f"  · 사분면(ROE>10%&PBR<1): {int(u['rim_quadrant'].sum() if u['rim_quadrant'].notna().any() else 0)}개")
    gate = u['quality_gate']
    print(f"품질게이트: 통과 {int((gate == 1).sum())} / 탈락 {int((gate == 0).sum())} / 자료없음 {int(gate.isna().sum())}")
    fresh = (u['stage3_src_run'].astype(str) == str(run_id)).sum()
    print(f"stage3 운반값 신선도: 당일 run {fresh}개 / 과거 run {int(u['stage3_src_run'].notna().sum()) - fresh}개")
    chk = u.dropna(subset=['rim_spread']).sort_values('rim_spread')
    if len(chk) >= 6:
        print("\n[데이터 정합성 점검용 — 추천 아님] rim_spread 상·하위 3:")
        for _, r in pd.concat([chk.tail(3).iloc[::-1], chk.head(3)]).iterrows():
            print(f"   {r['name']}({r['ticker']}) spread {r['rim_spread']:+.2f} "
                  f"(ROE {r['roe_value']:.1f}%, PBR {r['pbr']:.2f})"
                  f"{' [우선주]' if r['is_pref'] else ''}{' [금융]' if r['is_financial'] else ''}")
    print("=" * 64)


# ============================================================
def main():
    ap = argparse.ArgumentParser(description="대형 가치주 트랙 2단계 — v1 관측 팩터 적재(점수 없음)")
    ap.add_argument("--run-id", default=None, help="기본: large_universe 최신 run")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--dry-run", action="store_true", help="리포트만, DB 미적재")
    args = ap.parse_args()

    db = Path(args.db)
    run_id = args.run_id or latest_universe_run(db)
    print("=" * 64)
    print(f"🏛️  대형 가치주 트랙 — 2단계: v1 관측 팩터 (run {run_id}, 관측 전용)")
    print("=" * 64)

    uni = load_universe(run_id, db)
    uni = apply_sector_overlay(uni, load_sector_map())
    n_mi = (uni['sector'] == '미분류').sum()
    print(f"   • 유니버스: {len(uni)}개 (rank≤{UNIVERSE_N} 분석 대상 {min(len(uni), UNIVERSE_N)}개)")
    print(f"   • 업종 오버레이: 금융 {(uni['sector']=='금융').sum()} · 지주 {(uni['sector']=='지주').sum()} · "
          f"리츠 {(uni['sector']=='리츠').sum()} · 미분류 잔여 {n_mi} (원라벨=sector_raw)")
    val = load_valuation(run_id)
    df = uni.merge(val, on='ticker', how='left')
    print(f"   • valuation 조인: PBR 보유 {df['pbr'].notna().sum()}/{len(df)}")

    s3 = load_stage3_latest(df['ticker'], run_id, db)
    df = df.merge(s3, on='ticker', how='left')
    print(f"   • stage3 운반(ocf/수급/YoY): {df['stage3_src_run'].notna().sum()}/{len(df)} (PIT: src ≤ {run_id})")

    bb, bb_mode = load_buyback(run_id)
    df = df.merge(bb, on='ticker', how='left')
    df['buyback_src'] = df.get('buyback_src', pd.Series(index=df.index, dtype=object)).fillna('미수집')
    cov = (df['buyback_src'] != '미수집').sum()
    print(f"   • 자사주 소각: 소스={bb_mode} → 확인 {cov}/{len(df)}종목 (미확인=NaN)")

    df = compute_factors(df)
    report(df, run_id)

    if args.dry_run:
        print("\n(dry-run — DB 미적재)")
    else:
        save_db(df, run_id, db)
    print("\n✅ 2단계 완료. 누적되면 §9(h=60/120d, 주간 평가)로 IC 검증 → 그 뒤에만 가중.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 실패: {e}")
        sys.exit(1)
