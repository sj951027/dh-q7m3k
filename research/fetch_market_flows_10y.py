# -*- coding: utf-8 -*-
"""시장 수급(투자자별 매수·매도·순매수 대금·수량) 10년 수집기 — 연구 전용, 운영 배치와 분리 (2026-10-31)

명세: research/handoff/REPLY_20261031_flow_data_spec.md(Codex) + CLAUDE_20261031_flow_data_spec_check.md. 탐색 조회(10/31) 실측: 2015-01-02 수록 · 상세 11열 · 단위 원 · 보존식 성립 · 로그인 필요(배치 .env 경로).
대상: KOSPI · KOSDAQ, 상세(detail=True) 11구분 + '전체', 매수/매도/순매수 각각(대금·수량), 보조로 일반(detail=False) 순매수(기관합계·외국인합계 검증용).
저장: C:\\...\\dh-q7m3k-data\\market_flows_10y.db (운영 DB 와 별개)
  investor_daily(market, date, investor, buy_val, sell_val, net_val, buy_qty, sell_qty, net_qty, is_aggregate, fetched_at, source)  PK(market,date,investor)
  agg_daily(market, date, investor, net_val, fetched_at)  — 일반 조회(기관합계·기타법인·개인·외국인합계·전체)
  meta(key, value) — 단위(KRW/SHARE)·범위·pykrx 버전·수집 시각
호출: 시장 2 × (대금 3 + 수량 3 + 일반 1) = 14회(각각 pykrx 가 730일 단위로 쪼개 보내며 1초 간격) ≈ 90요청, 2~3분.
품질 검사 5개(명세 §7)는 --check 로 따로(네트워크 없음): 보존식·거래대금 비율·daily_flows 한 달 대조·결측/휴장/중복·연속성.
실행: python research/fetch_market_flows_10y.py            (수집 + 검사)
      python research/fetch_market_flows_10y.py --check    (검사만)
      옵션 --start 20150101 --end YYYYMMDD --markets KOSPI,KOSDAQ --dry(네트워크 없이 계획만)
주의: 로그인은 .env(KRX_ID/KRX_PW) 를 market_series._load_dotenv 가 올리고 pykrx 가 import 때 수행한다(값 출력 없음). 평일 20:10~22:30 실행 금지. 재실행은 같은 키를 덮어쓴다(REPLACE) — 이전 값은 revision 표에 남긴다."""
import argparse, sqlite3, sys, time
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent; REPO = HERE.parent; sys.path.insert(0, str(REPO))
DB = REPO / ".." / "dh-q7m3k-data" / "market_flows_10y.db"
OPS = REPO / ".." / "dh-q7m3k-data" / "ohlcv.db"
OUT = HERE / "out_market_flows"; OUT.mkdir(exist_ok=True)
DETAIL = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금", "기타법인", "개인", "외국인", "기타외국인", "전체"]
INST7 = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
AGG = {"전체", "기관합계", "외국인합계"}
SOURCE = "KRX via pykrx 1.2.8 MDCSTAT02203/02202 (etf/etn/elw=False, detail)"


def say(s, log):
    print(s); log.append(s)


def ensure_db(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS investor_daily(market TEXT, date TEXT, investor TEXT, buy_val INTEGER, sell_val INTEGER, net_val INTEGER,
        buy_qty INTEGER, sell_qty INTEGER, net_qty INTEGER, is_aggregate INTEGER, fetched_at TEXT, source TEXT, PRIMARY KEY(market,date,investor));
    CREATE TABLE IF NOT EXISTS investor_daily_revision(market TEXT, date TEXT, investor TEXT, buy_val INTEGER, sell_val INTEGER, net_val INTEGER,
        buy_qty INTEGER, sell_qty INTEGER, net_qty INTEGER, fetched_at TEXT, replaced_at TEXT);
    CREATE TABLE IF NOT EXISTS agg_daily(market TEXT, date TEXT, investor TEXT, net_val INTEGER, fetched_at TEXT, PRIMARY KEY(market,date,investor));
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)


def fetch(market, start, end, log):
    from pykrx import stock
    got = {}
    for kind, fn in [("val", stock.get_market_trading_value_by_date), ("qty", stock.get_market_trading_volume_by_date)]:
        for on in ["매수", "매도", "순매수"]:
            t1 = time.time()
            try:
                df = fn(start, end, market, etf=False, etn=False, elw=False, on=on, detail=True)
            except Exception as e:                                   # 수량 함수는 탐색 조회로 확인 안 함 → 실패하면 수량만 비움
                if kind == "qty":
                    say(f"  {market} qty {on}: 실패({type(e).__name__}) → 수량 열 NULL", log); got[(kind, on)] = pd.DataFrame(); continue
                raise
            say(f"  {market} {kind} {on}: {len(df)}행 · 열 {len(df.columns)} · {time.time()-t1:.0f}s", log)
            if list(df.columns) != DETAIL:
                if kind == "qty":
                    say(f"  ⚠ 수량 열 집합이 다름: {list(df.columns)} → 수량 열 NULL", log); got[(kind, on)] = pd.DataFrame(); continue
                say(f"  ⚠ 열 집합이 다름: {list(df.columns)} — 저장 중단", log); return None, None
            got[(kind, on)] = df
            time.sleep(1)
    t1 = time.time()
    agg = stock.get_market_trading_value_by_date(start, end, market, etf=False, etn=False, elw=False, on="순매수", detail=False)
    say(f"  {market} 일반 순매수: {len(agg)}행 · 열 {list(agg.columns)} · {time.time()-t1:.0f}s", log)
    return got, agg


def to_rows(market, got, agg, fetched_at):
    rows, arows = [], []
    idx = got[("val", "순매수")].index
    for d in idx:
        ds = pd.Timestamp(d).strftime("%Y%m%d")
        for inv in DETAIL:
            def g(kind, on):
                df = got[(kind, on)]
                return int(df.at[d, inv]) if (len(df) and d in df.index and inv in df.columns and pd.notna(df.at[d, inv])) else None
            rows.append((market, ds, inv, g("val", "매수"), g("val", "매도"), g("val", "순매수"), g("qty", "매수"), g("qty", "매도"), g("qty", "순매수"),
                         1 if inv in AGG else 0, fetched_at, SOURCE))
    for d in agg.index:
        ds = pd.Timestamp(d).strftime("%Y%m%d")
        for inv in agg.columns:
            v = agg.at[d, inv]; arows.append((market, ds, inv, int(v) if pd.notna(v) else None, fetched_at))
    return rows, arows


def store(con, rows, arows, fetched_at):
    cur = con.cursor()
    # 이전 값 보존(값이 달라진 행만 revision 으로)
    old = {(m, d, i): r for m, d, i, *r in cur.execute("SELECT market,date,investor,buy_val,sell_val,net_val,buy_qty,sell_qty,net_qty,fetched_at FROM investor_daily")}
    nrev = 0
    for r in rows:
        k = (r[0], r[1], r[2])
        if k in old and tuple(old[k][:6]) != tuple(r[3:9]):
            cur.execute("INSERT INTO investor_daily_revision VALUES(?,?,?,?,?,?,?,?,?,?,?)", (*k, *old[k][:6], old[k][6], fetched_at)); nrev += 1
    cur.executemany("INSERT OR REPLACE INTO investor_daily VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    cur.executemany("INSERT OR REPLACE INTO agg_daily VALUES(?,?,?,?,?)", arows)
    con.commit(); return nrev


def check(con, log):
    """품질 검사 5개 — 네트워크 없음."""
    df = pd.read_sql("SELECT * FROM investor_daily", con)
    if df.empty:
        say("검사: 자료 없음", log); return
    det = df[df.is_aggregate == 0]
    say(f"\n== 검사 1. 보존식 ==", log)
    bad1 = df[(df.buy_val - df.sell_val - df.net_val).abs() > 0]; say(f"  매수−매도=순매수 위반 행: {len(bad1)} / {len(df)}", log)
    s = det.groupby(["market", "date"]).net_val.sum(); say(f"  11구분 순매수 합 ≠ 0 인 날: {(s != 0).sum()} / {len(s)} (최대 |합| {s.abs().max():,})", log)
    agg = pd.read_sql("SELECT * FROM agg_daily", con)
    if not agg.empty:
        inst = det[det.investor.isin(INST7)].groupby(["market", "date"]).net_val.sum().rename("inst7")
        a = agg[agg.investor == "기관합계"].set_index(["market", "date"]).net_val.rename("agg_val")      # 열 이름 'agg' 는 DataFrame.agg 메서드와 겹쳐 비교가 깨짐(10/31 실측)
        j = pd.concat([inst, a], axis=1).dropna(); say(f"  기관합계 = 7개 합 위반: {(j.inst7 != j.agg_val).sum()} / {len(j)}", log)
        fo = det[det.investor.isin(["외국인", "기타외국인"])].groupby(["market", "date"]).net_val.sum().rename("f2")
        a2 = agg[agg.investor == "외국인합계"].set_index(["market", "date"]).net_val.rename("agg_val")
        j2 = pd.concat([fo, a2], axis=1).dropna(); say(f"  외국인합계 = 외국인+기타외국인 위반: {(j2.f2 != j2.agg_val).sum()} / {len(j2)}", log)
    say(f"\n== 검사 2. 거래대금 비율(매수 전체 = 매도 전체 = T, 구분별 매수/T·매도/T ∈ [0,1]) ==", log)
    tot = df[df.investor == "전체"].set_index(["market", "date"])
    say(f"  매수 전체 ≠ 매도 전체 인 날: {(tot.buy_val != tot.sell_val).sum()} / {len(tot)}", log)
    m = det.merge(tot[["buy_val"]].rename(columns={"buy_val": "T"}), left_on=["market", "date"], right_index=True)
    m = m[m["T"] > 0]; r = pd.concat([m.buy_val / m["T"], m.sell_val / m["T"]])
    say(f"  비율 범위 [{r.min():.3f}, {r.max():.3f}] · 범위 밖 행 {(r.lt(0) | r.gt(1)).sum()}", log)
    try:
        ops = sqlite3.connect(f"file:{OPS}?mode=ro", uri=True)
        tv = pd.read_sql("SELECT market, date, sum(volume*close) AS tv FROM daily_ohlcv GROUP BY 1,2", ops)
        jj = tot.reset_index().merge(tv, on=["market", "date"]); jj["ratio"] = jj.buy_val / jj.tv
        say(f"  운영 DB Σ(volume×close) 대비 매수 전체 비율(시장별 중앙값): " + " · ".join(f"{k} {v:.3f}" for k, v in jj.groupby("market").ratio.median().items()) + f" · n {len(jj)}", log)
        say(f"\n== 검사 3. daily_flows(종목별 KIS, 2026-04-28~) 와 한 달(2026-05) 대조 ==", log)
        fl = pd.read_sql("""SELECT o.market, f.date, sum(f.foreign_net_qty) fq, sum(f.foreign_net_val)*1000000 fv, sum(f.person_net_qty) pq, sum(f.person_net_val)*1000000 pv,
                            sum(f.pension_net_qty) nq, sum(f.pension_net_val)*1000000 nv, count(*) n
                            FROM daily_flows f JOIN (SELECT ticker, max(market) market FROM daily_ohlcv GROUP BY ticker) o ON o.ticker=f.ticker
                            WHERE f.date BETWEEN '20260501' AND '20260531' GROUP BY 1,2""", ops); ops.close()
        for inv, q, v in [("외국인", "fq", "fv"), ("개인", "pq", "pv"), ("연기금", "nq", "nv")]:
            k = det[(det.investor == inv) & (det.date.between("20260501", "20260531"))][["market", "date", "net_qty", "net_val"]].merge(fl, on=["market", "date"])
            if len(k):
                cq = k[["net_qty", q]].corr().iloc[0, 1]; cv = k[["net_val", v]].corr().iloc[0, 1]
                rq = (k[q] / k.net_qty.replace(0, pd.NA)).median(); rv = (k[v] / k.net_val.replace(0, pd.NA)).median()
                say(f"  {inv}: 날 {len(k)} · 수량 상관 {cq:.3f}(종목합/시장 중앙 {rq:.2f}) · 대금 상관 {cv:.3f}(중앙 {rv:.2f}) · 종목 수 {int(fl.n.median())}", log)
    except Exception as e:
        say(f"  (운영 DB 대조 생략: {e})", log)
    say(f"\n== 검사 4. 결측·휴장·중복 ==", log)
    try:
        ops = sqlite3.connect(f"file:{OPS}?mode=ro", uri=True)
        td = pd.read_sql("SELECT DISTINCT market, date FROM daily_ohlcv WHERE date >= '20230601'", ops); ops.close()
        have = tot.reset_index()[["market", "date"]]
        miss = td.merge(have, how="left", indicator=True); miss = miss[miss._merge == "left_only"]
        extra = have[have.date >= "20230601"].merge(td, how="left", indicator=True); extra = extra[extra._merge == "left_only"]
        say(f"  운영 DB 거래일(2023-06~)인데 수급 없는 날: {len(miss)} · 수급은 있는데 운영 DB 에 없는 날: {len(extra)}", log)
    except Exception as e:
        say(f"  (휴장 대조 생략: {e})", log)
    dup = df.duplicated(["market", "date", "investor"]).sum(); say(f"  키 중복: {dup} · 결측 셀: {int(df[['buy_val','sell_val','net_val']].isna().sum().sum())}", log)
    say(f"\n== 검사 5. 연속성(연도별 날 수·구분 수·전체 거래대금 중앙값) ==", log)
    y = tot.reset_index(); y["year"] = y.date.str[:4]
    say(y.groupby(["market", "year"]).agg(days=("date", "nunique"), T_med=("buy_val", "median")).assign(T_med=lambda x: (x.T_med / 1e12).round(2)).to_string(), log)
    say(f"  구분 수(날마다 같아야): {det.groupby(['market','date']).investor.nunique().value_counts().to_dict()}", log)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default="20150101"); ap.add_argument("--end", default=datetime.now().strftime("%Y%m%d"))
    ap.add_argument("--markets", default="KOSPI,KOSDAQ"); ap.add_argument("--check", action="store_true"); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(); log = []
    now = datetime.now()
    if now.weekday() < 5 and "20:10" <= now.strftime("%H:%M") <= "22:30" and not a.check:
        print("평일 20:10~22:30 — 배치 시간이라 실행하지 않음"); return
    con = sqlite3.connect(DB); ensure_db(con)
    if not a.check:
        if a.dry:
            say(f"[dry] {a.markets} {a.start}~{a.end} → {DB} (호출 14회)", log); return
        import market_series; market_series._load_dotenv()          # .env → os.environ (값 출력 없음)
        fetched_at = now.strftime("%Y-%m-%d %H:%M:%S")
        for mk in a.markets.split(","):
            say(f"\n[{mk}] {a.start}~{a.end}", log)
            got, agg = fetch(mk, a.start, a.end, log)
            if got is None:
                continue
            rows, arows = to_rows(mk, got, agg, fetched_at); nrev = store(con, rows, arows, fetched_at)
            say(f"  저장 {len(rows)}행(revision {nrev}) · 일반 {len(arows)}행", log)
        for k, v in {"val_unit": "KRW", "qty_unit": "SHARE", "unit_verified": "2026-10-31 probe: 매수 전체 / Σ(volume×close) = 1.009 (KOSPI 20261029)",
                     "scope": "etf=etn=elw=False, detail=True, markets=" + a.markets, "last_fetch": fetched_at, "range": f"{a.start}~{a.end}", "source": SOURCE}.items():
            con.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))
        con.commit()
    check(con, log); con.close()
    (OUT / f"quality_{now.strftime('%Y%m%d_%H%M')}.txt").write_text("\n".join(log), encoding="utf-8")
    print(f"\n→ {DB} · 로그 {OUT}")


if __name__ == "__main__":
    main()
