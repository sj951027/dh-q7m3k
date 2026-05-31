#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diversify_picks.py — 섹터 쏠림 방지 (분산된 추천 리스트)
==========================================================
왜 필요한가:
  시장이 빠진 날엔 같은 업종(예: 건설·화학)이 통째로 떨어져서, 스크리너
  추천 상위가 한 업종으로 쏠린다. 그걸 다 사면 '분산'이 아니라 사실상
  한 곳에 몰빵이다. 이 도구는 '한 업종은 최대 N개까지'만 남겨, 점수는
  높지만 같은 업종이 줄줄이 들어오는 걸 막은 '분산 추천 리스트'를 만든다.

중요:
  - 점수(final_score)는 건드리지 않는다. 이미 매겨진 리스트에서 '고르는'
    단계일 뿐. → 검증(validate_scores)에서 보는 점수 품질에 영향 없음.
  - 스크리너 자동 파이프라인(GitHub Actions)과 무관. 네가 돌릴 때만 동작.

업종(sector) 데이터 출처 (위에서부터 우선):
  1) sector_overrides.csv  ← 네가 직접 채우는 표 (가장 정확, 선택)
  2) sector_cache.json     ← 한 번 조회한 업종을 저장해 재사용 (자동)
  3) FinanceDataReader 종목목록의 업종 컬럼 (있으면)
  → 끝내 못 찾으면 '미분류'. 미분류는 서로 묶지 않고 각각 별개로 취급
    (모르는 종목을 같은 업종으로 잘못 합치지 않기 위해).

사용법:
    python diversify_picks.py                      # 최신 결과, 업종당 최대 3개
    python diversify_picks.py --market kospi --top 20 --max-per-sector 3
    python diversify_picks.py --source db          # CSV 대신 history.db에서
    python diversify_picks.py --demo               # 예시(가짜 데이터)로 동작 확인

결과물:
    - 화면: 원본 vs 분산 후 업종 분포 + 분산된 추천 표
    - diversified_picks_*.csv

업종을 직접 채우려면 sector_overrides.csv 를 이렇게 만들면 됨 (헤더 포함):
    ticker,sector
    000720,건설
    011170,화학
"""

import argparse
import glob
import json
import os
import sys

import pandas as pd

# ── 설정 ──────────────────────────────────────────────
DEFAULT_MAX_PER_SECTOR = 3
DEFAULT_TOP = 20
CACHE_FILE = "sector_cache.json"
OVERRIDE_FILE = "sector_overrides.csv"
UNKNOWN = "미분류"

# DART 산업분류코드(KSIC) 앞 2자리 → 읽기 쉬운 업종명 (집중도 관리용 coarse 분류)
KSIC_DIV = {
    "01": "농림어업", "02": "농림어업", "03": "농림어업",
    "05": "광업", "06": "광업", "07": "광업", "08": "광업",
    "10": "식료품", "11": "음료", "12": "담배",
    "13": "섬유", "14": "의복", "15": "가죽·신발",
    "16": "목재", "17": "펄프·종이", "18": "인쇄",
    "19": "석유정제", "20": "화학", "21": "제약·바이오",
    "22": "고무·플라스틱", "23": "비금속광물(시멘트·유리)", "24": "철강·1차금속",
    "25": "금속가공", "26": "반도체·전자부품", "27": "의료·정밀·광학",
    "28": "전기장비", "29": "기계·장비", "30": "자동차·부품",
    "31": "조선·기타운송", "32": "가구", "33": "기타제조",
    "35": "전력·가스", "36": "수도·환경", "37": "수도·환경",
    "38": "수도·환경", "39": "수도·환경",
    "41": "건설", "42": "건설",
    "45": "자동차판매", "46": "도매", "47": "소매",
    "49": "운수·물류", "50": "운수·물류", "51": "운수·물류", "52": "운수·물류",
    "55": "숙박·음식", "56": "숙박·음식",
    "58": "출판·SW", "59": "미디어·엔터", "60": "방송",
    "61": "통신", "62": "IT서비스", "63": "IT서비스",
    "64": "금융(은행)", "65": "보험", "66": "금융보조",
    "68": "부동산", "70": "지주·전문서비스", "71": "엔지니어링",
    "72": "연구개발", "73": "전문서비스", "74": "전문서비스",
    "75": "사업지원", "85": "교육", "86": "보건·의료",
    "90": "예술·스포츠", "91": "예술·스포츠",
}


def ksic_to_sector(induty_code):
    """DART induty_code(KSIC) → 업종명. 앞 2자리 기준."""
    if not induty_code:
        return None
    code = str(induty_code).strip().zfill(2)
    return KSIC_DIV.get(code[:2])


# ─────────────────────────────────────────────────────────────
# 업종 해석기 (캐시 + override + FDR)
# ─────────────────────────────────────────────────────────────
class SectorResolver:
    def __init__(self, cache_file=CACHE_FILE, override_file=OVERRIDE_FILE, dart_api_key=None):
        self.cache_file = cache_file
        self.dart_api_key = dart_api_key or os.environ.get("DART_API_KEY", "")
        self.cache = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}
        # 사용자 직접 입력(최우선)
        self.overrides = {}
        if os.path.exists(override_file):
            try:
                ov = pd.read_csv(override_file, dtype=str)
                ov["ticker"] = ov["ticker"].astype(str).str.zfill(6)
                self.overrides = dict(zip(ov["ticker"], ov["sector"].astype(str).str.strip()))
                print(f"   🏷️  {override_file}에서 {len(self.overrides)}개 업종 직접지정 로드")
            except Exception as e:
                print(f"   ⚠️  {override_file} 읽기 실패: {e}")
        self._fdr_map = None  # FDR 종목목록 업종 (lazy)
        self._dart_warned = False

    def _load_fdr_sectors(self):
        """FDR StockListing에서 업종 컬럼을 한 번만 긁어 dict로."""
        if self._fdr_map is not None:
            return self._fdr_map
        self._fdr_map = {}
        try:
            import FinanceDataReader as fdr
            for mkt in ("KRX", "KOSPI", "KOSDAQ"):
                try:
                    df = fdr.StockListing(mkt)
                except Exception:
                    continue
                if df is None or df.empty:
                    continue
                code_col = next((c for c in ["Code", "code", "Symbol", "종목코드"]
                                 if c in df.columns), None)
                sec_col = next((c for c in ["Sector", "sector", "Industry",
                                            "industry", "IndustryName", "업종"]
                                if c in df.columns), None)
                if not code_col or not sec_col:
                    continue
                for _, r in df[[code_col, sec_col]].dropna().iterrows():
                    code = str(r[code_col]).zfill(6)
                    sec = str(r[sec_col]).strip()
                    if code and sec and code not in self._fdr_map:
                        self._fdr_map[code] = sec
                if self._fdr_map:
                    print(f"   🏷️  FDR {mkt} 목록에서 업종 {len(self._fdr_map)}개 확보")
                    break
        except Exception as e:
            print(f"   ⚠️  FDR 업종 조회 불가: {type(e).__name__}")
        return self._fdr_map

    def _dart_sector(self, corp_code):
        """DART company.json → induty_code → 업종명. 실패 시 None."""
        if not self.dart_api_key or not corp_code:
            return None
        try:
            import requests
            code = str(corp_code).split(".")[0].zfill(8)
            url = "https://opendart.fss.or.kr/api/company.json"
            r = requests.get(url, params={"crtfc_key": self.dart_api_key, "corp_code": code},
                             timeout=10)
            j = r.json()
            if j.get("status") != "000":
                return None
            return ksic_to_sector(j.get("induty_code"))
        except Exception:
            if not self._dart_warned:
                print("   ⚠️  DART 업종 조회 중 오류 — 일부 종목은 미분류 처리")
                self._dart_warned = True
            return None

    def resolve(self, ticker, corp_code=None):
        t = str(ticker).zfill(6)
        if t in self.overrides:
            return self.overrides[t]
        if t in self.cache and self.cache[t] and self.cache[t] != UNKNOWN:
            return self.cache[t]
        # 1) FDR 종목목록 업종
        sec = self._load_fdr_sectors().get(t)
        # 2) DART 산업분류코드 (FDR이 못 주면)
        if not sec:
            sec = self._dart_sector(corp_code)
        sec = sec or UNKNOWN
        self.cache[t] = sec
        return sec

    def save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=0)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# 섹터 캡 알고리즘 (핵심)
# ─────────────────────────────────────────────────────────────
def diversify(df, max_per_sector=DEFAULT_MAX_PER_SECTOR, top=DEFAULT_TOP,
              score_col="final_score", sector_col="sector"):
    """점수 내림차순으로 보되, 한 업종이 max_per_sector를 넘으면 건너뛴다.
    '미분류'는 각각 별개로 취급(서로 묶어 자르지 않음). top개 채우면 종료.

    Returns: (kept_df, cut_df) — 둘 다 'sector','keep_reason' 포함.
    """
    d = df.sort_values(score_col, ascending=False).reset_index(drop=True)
    counts = {}
    kept_rows, cut_rows = [], []
    unknown_idx = 0
    for _, row in d.iterrows():
        sec = row.get(sector_col) or UNKNOWN
        # 미분류는 절대 묶지 않음 → 매번 고유 키
        key = sec if sec != UNKNOWN else f"{UNKNOWN}#{unknown_idx}"
        if sec == UNKNOWN:
            unknown_idx += 1

        if len(kept_rows) >= top:
            r = row.to_dict(); r["keep_reason"] = f"정원({top}) 초과"
            cut_rows.append(r); continue

        n = counts.get(key, 0)
        if n >= max_per_sector:
            r = row.to_dict()
            r["keep_reason"] = f"'{sec}' 업종 {max_per_sector}개 초과로 보류"
            cut_rows.append(r); continue

        counts[key] = n + 1
        r = row.to_dict(); r["keep_reason"] = "선정"
        kept_rows.append(r)

    return pd.DataFrame(kept_rows), pd.DataFrame(cut_rows)


def sector_distribution(df, sector_col="sector"):
    s = df[sector_col].fillna(UNKNOWN).replace("", UNKNOWN)
    return s.value_counts()


# ─────────────────────────────────────────────────────────────
# 입력 로드
# ─────────────────────────────────────────────────────────────
def load_latest_picks(source, market):
    if source == "db":
        import sqlite3
        if not os.path.exists("history.db"):
            print("❌ history.db가 없습니다."); sys.exit(1)
        conn = sqlite3.connect("history.db")
        q = ("SELECT market, ticker, name, sector, final_score FROM stage3_final "
             "WHERE run_id = (SELECT MAX(run_id) FROM stage3_final)")
        df = pd.read_sql(q, conn); conn.close()
        if market:
            df = df[df["market"] == market]
        return df

    # CSV (기본): latest_*_final.csv 또는 v2_*_final_*.csv 중 최신
    frames = []
    markets = [market] if market else ["kospi", "kosdaq"]
    for mkt in markets:
        path = f"latest_{mkt}_final.csv"
        if not os.path.exists(path):
            cands = sorted(glob.glob(f"v2_{mkt}_final_*.csv")
                           + glob.glob(f"**/v2_{mkt}_final_*.csv", recursive=True),
                           reverse=True)
            path = cands[0] if cands else None
        if not path:
            continue
        df = pd.read_csv(path, dtype={"ticker": str})
        if "market" not in df.columns:
            df["market"] = mkt
        frames.append(df)
        print(f"   ✓ {mkt}: {path} ({len(df)}개)")
    if not frames:
        print("❌ 스크리너 결과 CSV를 찾지 못했습니다 (latest_*_final.csv).")
        sys.exit(1)
    return pd.concat(frames, ignore_index=True)


# ─────────────────────────────────────────────────────────────
# 출력
# ─────────────────────────────────────────────────────────────
def print_report(market, raw, kept, cut, max_per_sector, top):
    bar = "=" * 64
    print(f"\n{bar}\n  🧭 섹터 쏠림 방지 — {market or 'KOSPI+KOSDAQ'}\n{bar}")
    print(f"  규칙: 업종당 최대 {max_per_sector}개, 총 {top}개 선정\n")

    raw_top = raw.sort_values("final_score", ascending=False).head(top)
    print(f"  [원본 상위 {top}개] 업종 분포:")
    for sec, n in sector_distribution(raw_top).items():
        flag = "  ⚠️ 쏠림" if n > max_per_sector else ""
        print(f"     {sec:<14} {n}개{flag}")

    print(f"\n  [분산 후 {len(kept)}개] 업종 분포:")
    for sec, n in sector_distribution(kept).items():
        print(f"     {sec:<14} {n}개")

    print(f"\n  {'─'*60}\n  ✅ 분산된 추천 리스트\n  {'─'*60}")
    print(f"  {'종목명':<12} {'업종':<12} {'점수':>7}")
    for _, r in kept.iterrows():
        print(f"  {str(r['name'])[:12]:<12} {str(r.get('sector') or UNKNOWN)[:12]:<12} "
              f"{r['final_score']:>7.1f}")

    if len(cut) and (cut["keep_reason"].str.contains("초과로 보류").any()):
        print(f"\n  {'─'*60}\n  ⏸️  쏠림으로 보류된 종목 (점수는 높지만 같은 업종 초과)\n  {'─'*60}")
        held = cut[cut["keep_reason"].str.contains("초과로 보류")].head(15)
        for _, r in held.iterrows():
            print(f"  {str(r['name'])[:12]:<12} {str(r.get('sector') or UNKNOWN)[:12]:<12} "
                  f"{r['final_score']:>7.1f}  ({r['keep_reason']})")
    print(bar)


# ─────────────────────────────────────────────────────────────
# demo / main
# ─────────────────────────────────────────────────────────────
def demo():
    print("🧪 예시: 건설·화학이 쏠린 가짜 추천에 '업종당 최대 3개' 적용\n")
    data = [
        ("성신양회", "건설", 114.4), ("일성건설", "건설", 112.6), ("SP삼화", "건설", 111.8),
        ("HL D&I", "건설", 107.0), ("다스코", "건설", 108.3),   # 건설 5개 → 3개로 제한
        ("한농화성", "화학", 109.7), ("SH에너지화학", "화학", 109.6),
        ("우성머티리얼스", "화학", 99.5), ("SG글로벌", "화학", 106.1),  # 화학 4개 → 3개
        ("케이뱅크", "금융", 105.4), ("보해양조", "음식료", 103.8),
        ("국제약품", "제약", 99.7), ("휴니드", "방산", 99.9),
        ("웅진", UNKNOWN, 101.2), ("미래아이앤지", UNKNOWN, 107.2),  # 미분류는 각각 별개
    ]
    df = pd.DataFrame(data, columns=["name", "sector", "final_score"])
    df["ticker"] = [f"{i:06d}" for i in range(len(df))]
    kept, cut = diversify(df, max_per_sector=3, top=10)
    print_report(None, df, kept, cut, 3, 10)


def main():
    ap = argparse.ArgumentParser(description="섹터 쏠림 방지 분산 추천")
    ap.add_argument("--market", choices=["kospi", "kosdaq"], default=None)
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--max-per-sector", type=int, default=DEFAULT_MAX_PER_SECTOR)
    ap.add_argument("--source", choices=["csv", "db"], default="csv")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        demo(); return

    print("📥 스크리너 결과 로드...")
    raw = load_latest_picks(args.source, args.market)
    raw["ticker"] = raw["ticker"].astype(str).str.zfill(6)
    raw["final_score"] = pd.to_numeric(raw["final_score"], errors="coerce")
    raw = raw.dropna(subset=["final_score"])

    # 업종 채우기 (override → cache → FDR → DART)
    has_sector = "sector" in raw.columns and raw["sector"].notna().any()
    if not has_sector:
        print("🏷️  업종 데이터가 비어 있어 업종을 해석합니다 (override→캐시→FDR→DART)...")
    resolver = SectorResolver()

    # 업종 조회는 점수 상위 후보에만 (하위는 어차피 컷 — DART 호출 절약)
    resolve_limit = max(args.top * 6, 60)
    has_corp = "corp_code" in raw.columns

    def resolve_row(r):
        if has_sector and pd.notna(r.get("sector")) and str(r.get("sector")).strip():
            return r["sector"]
        cc = r.get("corp_code") if has_corp else None
        return resolver.resolve(r["ticker"], cc)

    raw = raw.sort_values("final_score", ascending=False).reset_index(drop=True)
    raw["sector"] = UNKNOWN
    head_idx = (raw.groupby("market", group_keys=False)
                .apply(lambda g: g.head(resolve_limit)).index)
    raw.loc[head_idx, "sector"] = raw.loc[head_idx].apply(resolve_row, axis=1)
    resolver.save_cache()

    n_unknown = (raw["sector"] == UNKNOWN).sum()
    if n_unknown:
        print(f"   ⚠️  업종 미분류 {n_unknown}개 — 정확한 분산을 원하면 "
              f"{OVERRIDE_FILE}에 직접 채우세요 (ticker,sector).")

    # 업종이 채워진 '전체' CSV를 docs/에 저장 → 필터 페이지가 섹터 토글에 사용
    import os as _os
    docs_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "docs")
    _os.makedirs(docs_dir, exist_ok=True)
    for mkt in sorted(raw["market"].dropna().unique()):
        sub_all = raw[raw["market"] == mkt]
        out_path = _os.path.join(docs_dir, f"latest_{mkt}_enriched.csv")
        try:
            sub_all.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"   ✓ docs/latest_{mkt}_enriched.csv (업종 채운 전체, 필터용)")
        except Exception as e:
            print(f"   ⚠️  {mkt} enriched 저장 실패: {e}")

    # 시장별로 각각 분산 (한 시장 안에서 쏠림을 막는 게 의미 있음)
    out_frames = []
    for mkt in sorted(raw["market"].dropna().unique()) if not args.market else [args.market]:
        sub = raw[raw["market"] == mkt]
        if sub.empty:
            continue
        kept, cut = diversify(sub, args.max_per_sector, args.top)
        print_report(mkt, sub, kept, cut, args.max_per_sector, args.top)
        kept = kept.copy(); kept["market"] = mkt
        out_frames.append(kept)

    if out_frames:
        out = pd.concat(out_frames, ignore_index=True)
        cols = [c for c in ["market", "ticker", "name", "sector", "final_score", "keep_reason"]
                if c in out.columns]
        from datetime import datetime
        fn = f"diversified_picks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        out[cols].to_csv(fn, index=False, encoding="utf-8-sig")
        print(f"\n💾 저장: {fn}")


if __name__ == "__main__":
    main()
