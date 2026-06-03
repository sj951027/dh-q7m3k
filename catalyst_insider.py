# -*- coding: utf-8 -*-
"""
catalyst_insider.py  (댁의 PC에서 실행 — DART 네트워크 필요)
================================================================
'상승 촉매' 중 가장 견고한 두 가지를 DART에서 뽑아 점수화한다.
stage2_risk_filter_v2_6.py 의 DART 배관(get_corp_code_mapping / fetch_disclosures)
을 그대로 재사용하고, v3_rescore.attach_valuation 과 같은 패턴의 파일을 만든다:

    catalyst_kospi_{run_id}.csv
    catalyst_kosdaq_{run_id}.csv
    컬럼: ticker, name, insider_score, insider_net_irds, insider_buy_filings,
          insider_top_role, insider_recent_dt, insider_source,
          buyback_cancel_flag, buyback_cancel_dt, catalyst_score, catalyst_detail

────────────────────────────────────────────────────────────────
[설계 — 정직하게 짚는 한계]
DART 오픈API의 임원·주요주주 소유보고(elestock.json)는 '보고 시점의 소유수/증감'
요약만 준다. *취득/처분 사유(장내매수·스톡옵션행사·상속·증여·무상신주 …)* 는
보고서 '본문(세부변동내역)' 에 있고 API 요약엔 깨끗하게 들어오지 않는다.
그래서 이 스크립트는:
  • 사유 본문 파싱(깨지기 쉬움)은 '하지 않는다'.
  • 대신 다음 프록시로 *오염을 줄인다* (제거가 아니라 감축):
      - 소유수가 '증가'한 보고만 집계 (매도/처분 원천 제외)
      - 최대주주 / 등기임원 가중 (지배주주의 장내매수가 가장 강한 신호)
      - 아주 작은 증감은 무시 (ESOP·끝수·우리사주 노이즈 컷)
      - '반복 매수' 가점 (스톡옵션 행사는 보통 1회성, 장내 누적매수는 반복)
  • 단, elestock 응답에 '사유'로 보이는 필드가 실제로 있으면(있을 때만)
    그걸로 진짜 매수만 추가로 걸러낸다(_REASON_* 맵). 없으면 위 프록시로 진행하고
    insider_source 에 'PROXY' 로 표기한다 → 점수의 신뢰도를 호출부가 알 수 있게.

자기주식 '소각'은 공시 제목으로 깔끔히 잡히고(매수/매도 모호성 없음) 영구적
주주환원이라 별도 신호로 둔다. (자기주식 '취득'은 신탁·미집행 여지가 있어 제외.)

[중요] 여기서 매기는 점수는 '최종 가중치'가 아니라 *후보값*이다.
history.db 에 쌓아 validate_scores 의 IC(특히 기존 final_score 대비 '증분 IC')로
검증되기 전까지 final_score_v3 에 큰 가중을 주지 말 것. (column → IC → weight 순서)

설치(한 번만):  pip install requests pandas
DART 키 (.env 한 줄):  DART_API_KEY=...

실행:
    python catalyst_insider.py --market kospi
    python catalyst_insider.py --market kosdaq --days 90
    python catalyst_insider.py --self-test         # 네트워크 없이 점수 로직만 점검
"""
import argparse
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd


# ----------------------------------------------------------------- 설정
CACHE_DIR = "dart_cache"
DEFAULT_DAYS = 90          # 촉매는 '최근'이 핵심 (1~3개월). 너무 길면 신선도 희석.
MAX_WORKERS = 2            # stage2/stage3 와 동일하게 DART 부담 최소화
ELESTOCK_URL = "https://opendart.fss.or.kr/api/elestock.json"

# 자기주식 소각: 제목으로 깔끔히 잡히는 영구적 주주환원 신호.
# (취득/신탁계약은 미집행 여지가 있어 의도적으로 제외 → '소각'만.)
BUYBACK_CANCEL_KEYS = ["자기주식소각", "주식소각", "자사주소각"]

# elestock 응답에 '사유'로 보이는 필드가 있을 때만 사용하는 화이트/블랙리스트.
# (대개는 비어 있어 PROXY 경로로 빠진다. 있으면 진짜 매수만 통과.)
_REASON_FIELD_CANDIDATES = ["change_on", "chg_rs", "rs", "trdtp", "ctr_stockknd_rs"]
_REASON_BUY = ["장내매수", "장내매도외매수", "시간외매수", "공개매수"]
_REASON_BLOCK = [
    "장내매도", "장외매도", "시간외매도", "처분",
    "주식매수선택권", "스톡옵션", "신주인수권",
    "상속", "증여", "무상", "유상신주", "배정",
    "전환사채", "교환사채", "신규상장", "공모",
]


# ----------------------------------------------------------------- .env
def load_env(env_path=None):
    """.env 를 읽어 환경변수로 올린다. (fetch_valuation.py 와 동일 방식)"""
    p = Path(env_path) if env_path else (Path(__file__).resolve().parent / ".env")
    if not p.exists():
        print(f"[env] .env 파일을 찾지 못함: {p}")
        return
    n = 0
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            os.environ[key] = val
            n += 1
    print(f"[env] .env 에서 {n}개 키 로드")


# ----------------------------------------------------------------- 헬퍼
def _g(d, *keys, default=""):
    """dict 에서 후보 키들을 순서대로 시도(필드명 변형 방어)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


def _to_int(x):
    try:
        return int(str(x).replace(",", "").strip())
    except Exception:
        return 0


def _to_float(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except Exception:
        return 0.0


def _norm(s):
    return str(s or "").replace(" ", "")


def role_weight(item):
    """보고자 역할 가중치. 최대주주 장내매수가 가장 강한 신호."""
    main = _norm(_g(item, "isu_main_shrholdr"))
    rgist = _norm(_g(item, "isu_exctv_rgist_at"))   # '등기임원'/'비등기임원' 등
    if "최대주주" in main:
        return 1.0
    if main and main not in ("nan", "None", "-", "해당없음"):
        return 0.8                                  # 그 외 주요주주
    if "등기" in rgist and "비등기" not in rgist:
        return 0.7                                  # 등기임원
    return 0.4                                       # 비등기/기타


def _magnitude_factor(irds_cnt, irds_rate):
    """증감 크기 → 0.2~1.0. 비율(%p)이 있으면 우선, 없으면 수량 기준."""
    if irds_rate > 0:
        if irds_rate >= 0.5:
            return 1.0
        if irds_rate >= 0.2:
            return 0.7
        if irds_rate >= 0.05:
            return 0.4
        return 0.2
    # 비율 미제공 → 수량 기준 대략치
    if irds_cnt >= 50000:
        return 0.8
    if irds_cnt >= 10000:
        return 0.5
    if irds_cnt >= 1000:
        return 0.3
    return 0.2


def _reason_ok(item):
    """
    응답에 '사유' 필드가 있을 때만 진짜 매수인지 판정.
    반환: (판정가능?, 매수맞음?)  — 필드가 없으면 (False, _)
    """
    raw = ""
    for f in _REASON_FIELD_CANDIDATES:
        if f in item and item[f] not in (None, ""):
            raw = _norm(item[f])
            break
    if not raw:
        return False, False
    if any(b in raw for b in _REASON_BLOCK):
        return True, False
    if any(g in raw for g in _REASON_BUY):
        return True, True
    # 사유는 있는데 매수/차단 어느 쪽도 아니면 보수적으로 '아님' 처리
    return True, False


# ----------------------------------------------------------------- 점수
def score_insider(filings, days=DEFAULT_DAYS, asof=None):
    """
    한 종목의 elestock 보고 리스트 → 내부자 매집 점수(0~15) + 부가정보.
    '소유수 증가' 보고만 집계. 사유 필드가 있으면 진짜 매수만 추가 필터.
    asof: 기준일(datetime). 백테스트 시 룩어헤드 방지를 위해 이 날짜 '이전'
          접수 보고만 집계. (실시간 실행이면 None=오늘)
    """
    asof = asof or datetime.now()
    start = asof - timedelta(days=days)

    used = 0
    saw_reason_field = False
    net_irds = 0
    raw = 0.0
    top_role = 0.0
    recent_dt = ""

    for it in filings:
        # 날짜 윈도 + 룩어헤드 컷
        ds = _norm(_g(it, "rcept_dt"))
        if len(ds) >= 8:
            try:
                d = datetime.strptime(ds[:8], "%Y%m%d")
            except Exception:
                continue
            if d < start or d > asof:
                continue
        else:
            continue

        irds_cnt = _to_int(_g(it, "sp_stock_lmp_irds_cnt"))
        irds_rate = _to_float(_g(it, "sp_stock_lmp_irds_rate"))
        if irds_cnt <= 0 and irds_rate <= 0:
            continue                                  # 증가분만 (매도/무변동 제외)

        # 사유 필드가 (있다면) 진짜 매수만 통과
        can_judge, is_buy = _reason_ok(it)
        if can_judge:
            saw_reason_field = True
            if not is_buy:
                continue

        rw = role_weight(it)
        mf = _magnitude_factor(irds_cnt, irds_rate)
        raw += rw * mf
        net_irds += max(irds_cnt, 0)
        top_role = max(top_role, rw)
        used += 1
        if ds > recent_dt:
            recent_dt = ds

    if used == 0:
        return {
            "insider_score": 0.0, "insider_net_irds": 0, "insider_buy_filings": 0,
            "insider_top_role": 0.0, "insider_recent_dt": "",
            "insider_source": "NONE",
        }

    score = raw * 5.0                                 # raw(대략 0~3) → 0~15 스케일
    if used >= 3:                                     # 반복 매수 가점
        score += 3
    elif used >= 2:
        score += 1.5
    score = round(min(15.0, max(0.0, score)), 1)

    return {
        "insider_score": score,
        "insider_net_irds": int(net_irds),
        "insider_buy_filings": int(used),
        "insider_top_role": round(top_role, 2),
        "insider_recent_dt": recent_dt,
        # 사유 필드로 걸렀으면 VERIFIED, 프록시면 PROXY (신뢰도 표기)
        "insider_source": "VERIFIED" if saw_reason_field else "PROXY",
    }


def score_buyback_cancel(disclosures, days=DEFAULT_DAYS, asof=None):
    """공시 목록에서 자기주식 '소각' 결정만 탐지(제목 기반, 깔끔)."""
    asof = asof or datetime.now()
    start = asof - timedelta(days=days)
    hit_dt = ""
    for disc in disclosures:
        title = _norm(_g(disc, "report_nm"))
        if not any(k in title for k in BUYBACK_CANCEL_KEYS):
            continue
        if "취득" in title and not any(k in title for k in BUYBACK_CANCEL_KEYS):
            continue  # '취득'만이면 제외 (소각 키워드가 있으면 통과)
        ds = _norm(_g(disc, "rcept_dt"))[:8]
        if len(ds) == 8:
            try:
                d = datetime.strptime(ds, "%Y%m%d")
            except Exception:
                continue
            if d < start or d > asof:
                continue
            if ds > hit_dt:
                hit_dt = ds
    return {"buyback_cancel_flag": 1 if hit_dt else 0, "buyback_cancel_dt": hit_dt}


def combine_catalyst(ins, buy):
    """내부자 + 자사주소각 → catalyst_score(0~20) + 설명."""
    s = ins["insider_score"] + (8 if buy["buyback_cancel_flag"] else 0)
    s = round(min(20.0, max(0.0, s)), 1)
    bits = []
    if ins["insider_buy_filings"]:
        src = "" if ins["insider_source"] == "VERIFIED" else "(프록시)"
        bits.append(f"내부자매집{src} {ins['insider_buy_filings']}건/"
                    f"{ins['insider_net_irds']:,}주")
    if buy["buyback_cancel_flag"]:
        bits.append(f"자사주소각 {buy['buyback_cancel_dt']}")
    return {"catalyst_score": s, "catalyst_detail": " | ".join(bits)}


# ----------------------------------------------------------------- DART 조회
def fetch_elestock(corp_code, api_key, timeout=10):
    """임원·주요주주 소유보고(elestock). 실패 시 빈 리스트(파이프라인 안전)."""
    import requests   # 지연 임포트: self-test 는 네트워크 라이브러리 없이 동작
    try:
        resp = requests.get(
            ELESTOCK_URL,
            params={"crtfc_key": api_key, "corp_code": corp_code},
            timeout=timeout,
        )
        data = resp.json()
        if data.get("status") != "000":
            return []
        return data.get("list", []) or []
    except Exception:
        return []


# ----------------------------------------------------------------- v3 연동 훅
def attach_catalyst(df, run_id, market):
    """
    v3_rescore.attach_valuation 과 같은 패턴.
    catalyst_{market}_{run_id}.csv 가 있으면 catalyst_score 를 df 에 병합.
    없으면 0 + 플래그. (v3_rescore.py 에서 import 해서 쓰면 됨)
    """
    path = f"catalyst_{market}_{run_id}.csv"
    if not os.path.exists(path):
        df["catalyst_score"] = 0.0
        df["catalyst_source"] = "UNAVAILABLE"
        return df
    c = pd.read_csv(path, dtype={"ticker": str})
    c["ticker"] = c["ticker"].astype(str).str.zfill(6)
    keep = ["ticker", "catalyst_score", "insider_source",
            "buyback_cancel_flag", "catalyst_detail"]
    keep = [k for k in keep if k in c.columns]
    df = df.merge(c[keep], on="ticker", how="left")
    df["catalyst_score"] = pd.to_numeric(df.get("catalyst_score"),
                                         errors="coerce").fillna(0.0)
    df["catalyst_source"] = "DART"
    return df


# ----------------------------------------------------------------- 유니버스
def load_universe(market, input_csv=None):
    """검사 대상 종목(ticker[,name]). DART 부담을 줄이려 '후보'만 대상으로."""
    if input_csv and Path(input_csv).exists():
        path = input_csv
    else:
        cands = (sorted(Path(".").glob(f"v3_{market}_final_*.csv"), reverse=True)
                 or sorted(Path(".").glob(f"v2_{market}_filtered_safe_*.csv"), reverse=True))
        if not cands:
            raise SystemExit(
                f"[{market}] 입력 후보 CSV를 못 찾음. --input 으로 지정하거나 "
                f"먼저 스크리너/리스코어를 돌리세요.")
        path = str(cands[0])
    df = pd.read_csv(path, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    if "name" not in df.columns:
        df["name"] = df["ticker"]
    print(f"[{market}] 유니버스: {path}  ({len(df)}종목)")
    return df[["ticker", "name"]].drop_duplicates("ticker").reset_index(drop=True)


# ----------------------------------------------------------------- 메인
def run_market(market, api_key, run_id, days, input_csv, workers):
    import importlib
    stage2 = importlib.import_module("stage2_risk_filter_v2_6")  # 기업코드/공시목록 재사용

    uni = load_universe(market, input_csv)

    corp = stage2.get_corp_code_mapping(api_key)
    corp["stock_code"] = corp["stock_code"].str.zfill(6)
    uni = uni.merge(corp[["stock_code", "corp_code"]],
                    left_on="ticker", right_on="stock_code", how="left")
    miss = uni["corp_code"].isna().sum()
    if miss:
        print(f"   ⚠️  DART 미등록 {miss}개 제외")
    uni = uni.dropna(subset=["corp_code"]).reset_index(drop=True)

    rows_in = uni.to_dict("records")
    total = len(rows_in)
    print(f"   {total}개 종목 내부자/소각 조회 (병렬 {workers}스레드, 윈도 {days}일)")

    def one(r):
        time.sleep(0.05)
        elestock = fetch_elestock(r["corp_code"], api_key)
        ins = score_insider(elestock, days=days)
        # 자사주 소각은 일반 공시목록에서(stage2.fetch_disclosures 재사용)
        discs = stage2.fetch_disclosures(r["corp_code"], api_key, days_back=days)
        buy = score_buyback_cancel(discs, days=days)
        out = {"ticker": r["ticker"], "name": r["name"]}
        out.update(ins)
        out.update(buy)
        out.update(combine_catalyst(ins, buy))
        return out

    results = []
    done = 0
    lock = threading.Lock()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, r): r for r in rows_in}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                r = futs[fut]
                print(f"   ⚠️  {r.get('name', r['ticker'])} 실패: {e}")
            with lock:
                done += 1
                if done % 20 == 0 or done == total:
                    el = time.time() - t0
                    eta = (el / done) * (total - done) if done else 0
                    print(f"   [{done}/{total}] {el:.0f}s, 남은 ~{eta:.0f}s")

    out = pd.DataFrame(results)
    if out.empty:
        print(f"   [{market}] 결과 없음 — 파일 미생성")
        return
    out = out.sort_values("catalyst_score", ascending=False)
    out = out.replace(r"[\r\n]+", " ", regex=True)
    fn = f"catalyst_{market}_{run_id}.csv"
    out.to_csv(fn, index=False, encoding="utf-8-sig")

    n_ins = int((out["insider_buy_filings"] > 0).sum())
    n_buy = int(out["buyback_cancel_flag"].sum())
    n_proxy = int((out["insider_source"] == "PROXY").sum())
    print(f"   💾 {fn}  (내부자매집 {n_ins}종목 / 자사주소각 {n_buy}종목 / "
          f"프록시판정 {n_proxy}종목)")
    top = out[out["catalyst_score"] > 0].head(10)
    if not top.empty:
        print(f"\n   [{market.upper()}] 촉매 TOP")
        cols = ["name", "catalyst_score", "insider_buy_filings",
                "insider_source", "buyback_cancel_flag", "catalyst_detail"]
        print(top[[c for c in cols if c in top.columns]].to_string(index=False))


def self_test():
    """네트워크 없이 점수 로직만 검증 (가짜 elestock 레코드)."""
    print("── self-test: score_insider / buyback / combine ──")
    today = datetime.now().strftime("%Y%m%d")
    old = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

    # 1) 최대주주 장내 누적매수(반복) → 높은 점수, 사유필드 있어 VERIFIED
    f1 = [
        {"rcept_dt": today, "isu_main_shrholdr": "최대주주",
         "sp_stock_lmp_irds_cnt": "120,000", "sp_stock_lmp_irds_rate": "0.6",
         "chg_rs": "장내매수"},
        {"rcept_dt": today, "isu_main_shrholdr": "최대주주",
         "sp_stock_lmp_irds_cnt": "30,000", "sp_stock_lmp_irds_rate": "0.15",
         "chg_rs": "장내매수"},
    ]
    r1 = score_insider(f1, days=90)
    assert r1["insider_score"] > 8, r1
    assert r1["insider_source"] == "VERIFIED", r1
    assert r1["insider_buy_filings"] == 2, r1

    # 2) 사유=스톡옵션행사 → 사유필드로 차단되어 0
    f2 = [{"rcept_dt": today, "isu_exctv_rgist_at": "등기임원",
           "sp_stock_lmp_irds_cnt": "50,000", "sp_stock_lmp_irds_rate": "0.3",
           "chg_rs": "주식매수선택권행사"}]
    r2 = score_insider(f2, days=90)
    assert r2["insider_score"] == 0, r2

    # 3) 사유필드 없음 + 증가 → PROXY 로 집계됨
    f3 = [{"rcept_dt": today, "isu_main_shrholdr": "최대주주",
           "sp_stock_lmp_irds_cnt": "80,000", "sp_stock_lmp_irds_rate": "0.4"}]
    r3 = score_insider(f3, days=90)
    assert r3["insider_score"] > 0 and r3["insider_source"] == "PROXY", r3

    # 4) 소유수 감소(매도) → 제외되어 0
    f4 = [{"rcept_dt": today, "isu_main_shrholdr": "최대주주",
           "sp_stock_lmp_irds_cnt": "-90,000", "sp_stock_lmp_irds_rate": "-0.5"}]
    r4 = score_insider(f4, days=90)
    assert r4["insider_score"] == 0, r4

    # 5) 윈도 밖(400일 전) → 제외
    f5 = [{"rcept_dt": old, "isu_main_shrholdr": "최대주주",
           "sp_stock_lmp_irds_cnt": "90,000", "sp_stock_lmp_irds_rate": "0.5",
           "chg_rs": "장내매수"}]
    r5 = score_insider(f5, days=90)
    assert r5["insider_score"] == 0, r5

    # 6) 자사주 소각 탐지 / 취득은 무시
    d_ok = [{"report_nm": "주요사항보고서(자기주식소각결정)", "rcept_dt": today}]
    d_no = [{"report_nm": "주요사항보고서(자기주식취득결정)", "rcept_dt": today}]
    assert score_buyback_cancel(d_ok, days=90)["buyback_cancel_flag"] == 1
    assert score_buyback_cancel(d_no, days=90)["buyback_cancel_flag"] == 0

    # 7) 결합 점수: 소각이면 +8
    c = combine_catalyst(r1, {"buyback_cancel_flag": 1, "buyback_cancel_dt": today})
    assert abs(c["catalyst_score"] - min(20.0, r1["insider_score"] + 8)) < 1e-6, c

    print("   ✅ 통과:", {"r1": r1["insider_score"], "r2": r2["insider_score"],
                        "r3_src": r3["insider_source"], "combine": c["catalyst_score"]})
    print("   (실제 elestock 필드명은 PC에서 1회 실행해 확인 권장 — 아래 NOTE)")


def inspect(stock_code):
    """실제 elestock 응답의 '필드명'을 1종목으로 확인 (내가 못 본 부분 점검용).
    예: python catalyst_insider.py --inspect 005930"""
    import importlib
    load_env()
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if len(api_key) < 30:
        raise SystemExit("❌ DART_API_KEY 확인")
    stage2 = importlib.import_module("stage2_risk_filter_v2_6")
    corp = stage2.get_corp_code_mapping(api_key)
    corp["stock_code"] = corp["stock_code"].str.zfill(6)
    row = corp[corp["stock_code"] == str(stock_code).zfill(6)]
    if row.empty:
        raise SystemExit(f"기업코드 매핑에 {stock_code} 없음")
    cc = row["corp_code"].iloc[0]
    items = fetch_elestock(cc, api_key)
    print(f"[{stock_code}] elestock 보고 {len(items)}건")
    if items:
        import json
        print("첫 보고 필드명:", list(items[0].keys()))
        print("샘플:", json.dumps(items[0], ensure_ascii=False, indent=2)[:1200])
        print("\n→ 위 키들이 코드의 sp_stock_lmp_irds_cnt / sp_stock_lmp_irds_rate /"
              " isu_main_shrholdr / isu_exctv_rgist_at / rcept_dt 와 다르면 "
              "_g(...) 호출의 키만 바꿔주면 됨.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["kospi", "kosdaq"], default=None,
                    help="미지정 시 둘 다")
    ap.add_argument("--inspect", default=None, metavar="STOCK_CODE",
                    help="elestock 실제 필드명 확인용(1종목)")
    ap.add_argument("--run_id", default=None, help="기본: 오늘(YYYYMMDD)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS, help="조회 윈도(일)")
    ap.add_argument("--input", default=None, help="검사 대상 CSV(없으면 최신 후보 자동)")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--self-test", action="store_true",
                    help="네트워크 없이 점수 로직 점검")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    if args.inspect:
        inspect(args.inspect)
        return

    load_env()
    api_key = os.environ.get("DART_API_KEY", "").strip()
    if len(api_key) < 30:
        raise SystemExit("❌ .env 의 DART_API_KEY 가 비었거나 형식이 이상합니다.")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d")
    markets = [args.market] if args.market else ["kospi", "kosdaq"]
    for mkt in markets:
        print(f"\n{'='*64}\n▶  {mkt.upper()} 촉매(내부자매수+자사주소각) {run_id}\n{'='*64}")
        try:
            run_market(mkt, api_key, run_id, args.days, args.input, args.workers)
        except SystemExit as e:
            print(f"   건너뜀: {e}")


if __name__ == "__main__":
    main()
