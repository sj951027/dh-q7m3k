"""Research-only public macro collection and quality checks. No strategy analysis.

python -X utf8 -B research/fetch_macro_10y.py --collect --end 2026-10-31 --write-report
python -X utf8 -B research/fetch_macro_10y.py --check --write-report
python -X utf8 -B research/fetch_macro_10y.py --complete-missing --write-report
python -X utf8 -B research/fetch_macro_10y.py --self-check

Only the fixed NEW macro_10y.db may be created/written. Existing databases use
mode=ro/query_only. Collection refuses an existing target; check never fetches.
No .env, credentials, pykrx import, authentication, scheduler, or batch imports.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "dh-q7m3k-data"
TARGET = DATA / "macro_10y.db"
OPERATING = DATA / "ohlcv.db"
LONG_PRICE = DATA / "ohlcv_10y.db"
REPLY = ROOT / "research/handoff/REPLY_20261101_macro_10y_fetch.md"
ORDER = ("USDKRW", "VKOSPI", "SPX", "IXIC", "US10Y", "KR3Y", "WTI")
DDL = """
CREATE TABLE series_daily (
 series TEXT NOT NULL,
 date TEXT NOT NULL CHECK(length(date)=8 AND date NOT GLOB '*[^0-9]*'),
 close REAL NOT NULL,
 source TEXT NOT NULL,
 fetched_at TEXT NOT NULL,
 PRIMARY KEY(series,date)
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def guard():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.weekday() < 5 and "20:10" <= now.strftime("%H:%M") < "22:30":
        raise RuntimeError("평일 20:10~22:30 KST 파일/DB 작업 금지")
    return now.isoformat(timespec="seconds")


def state(path):
    guard()
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def ro(path):
    guard()
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    c.execute("PRAGMA query_only=ON")
    assert c.execute("PRAGMA query_only").fetchone()[0] == 1
    return c


def public_get(url, **kwargs):
    guard()
    with requests.Session() as session:
        session.trust_env = False  # No implicit .netrc authentication.
        response = session.get(url, timeout=(10,40), **kwargs)
        response.raise_for_status()
        return response


def canonicalize(frame, start, end):
    f = frame.copy()
    f["date"] = pd.to_datetime(f.date, errors="raise").dt.strftime("%Y%m%d")
    f["close"] = pd.to_numeric(f.close, errors="raise")
    f = f[(f.date >= start.replace("-", "")) & (f.date <= end.replace("-", ""))].copy()
    missing = int(f.close.isna().sum())
    f = f[f.close.notna()].copy()  # Missing days stay absent; never fill.
    if not np.isfinite(f.close).all():
        raise ValueError("Non-finite source value")
    duplicate = int(f.date.duplicated().sum())
    reverse = int((f.date.to_numpy()[1:] < f.date.to_numpy()[:-1]).sum())
    if duplicate:
        raise ValueError(f"Duplicate source dates: {duplicate}; not silently overwritten")
    f = f.sort_values("date",kind="stable").reset_index(drop=True)
    if f.empty:
        raise ValueError("No nonmissing observations in requested interval")
    return f, {"missing_source_values_omitted":missing,"source_duplicate_dates":duplicate,
               "source_descending_steps_before_sort":reverse}


def yahoo_fdr(key, symbol, start, end):
    """Use installed FDR values; recover provider-local date from its response.

    The installed reader normalizes UTC timestamps without exchange timezone.
    Capturing that same public response avoids a second fetch and preserves the
    exact date conversion, including London DST for KRW=X.
    """
    import FinanceDataReader as fdr
    captured = []
    original = requests.sessions.Session.request

    def bounded(session, method, url, **kwargs):
        guard()
        session.trust_env = False
        kwargs.setdefault("timeout", (10,40))
        response = original(session, method, url, **kwargs)
        if "/v8/finance/chart/" in url:
            captured.append(response)
        return response

    # Pad both ends, then strictly filter canonical source-local dates.
    fetch_start = (pd.Timestamp(start)-pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    fetch_end = (pd.Timestamp(end)+pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    with patch.object(requests.sessions.Session,"request",bounded), redirect_stdout(io.StringIO()):
        df = fdr.DataReader(symbol,fetch_start,fetch_end)
    if len(captured) != 1:
        raise ValueError("Expected one inspectable Yahoo response from FDR")
    response = captured[0]
    result = response.json()["chart"]["result"][0]
    metadata = result["meta"]
    expected = {"USDKRW":"KRW=X","SPX":"^GSPC","IXIC":"^IXIC"}.get(key)
    if expected and metadata.get("symbol") != expected:
        raise ValueError("Provider symbol does not match requested series")
    if key == "VKOSPI":
        description = " ".join(str(metadata.get(k,"")) for k in ("symbol","shortName","longName"))
        if metadata.get("instrumentType") != "INDEX" or not any(s in description.upper() for s in ("VKOSPI","V-KOSPI")):
            raise ValueError("Unverified VKOSPI instrument; rejected")
    timestamps = pd.to_datetime(result["timestamp"],unit="s",utc=True)
    local = timestamps.tz_convert(metadata["exchangeTimezoneName"])
    quotes = result["indicators"]["quote"][0]["close"]
    assert len(df) == len(quotes) and np.allclose(df.Close.to_numpy(float),np.array(quotes,float),equal_nan=True)
    raw = pd.DataFrame({"date":local.strftime("%Y-%m-%d"),"close":quotes,
                        "fdr_utc_date":timestamps.strftime("%Y%m%d")})
    f, qc = canonicalize(raw,start,end)
    m = {"status":"collected","provider":"Yahoo Finance via installed FinanceDataReader",
         "symbol":metadata["symbol"],"fdr_symbol":symbol,"fdr_version":fdr.__version__,
         "source_url":response.url,"response_sha256":hashlib.sha256(response.content).hexdigest(),
         "timezone":metadata["exchangeTimezoneName"],"date_semantics":"provider-local daily bar date",
         "fdr_utc_label_changes":int((f.date != f.fdr_utc_date).sum()),
         "fdr_date_map":dict(zip(f.date,f.fdr_utc_date)),"fetched_at":guard(),**qc}
    if key in ("SPX","IXIC"):
        m.update(unit="index_points",session_close="16:00 America/New_York; early closes no later than this",
                 availability="normal equity close in KST is next calendar day 05:00 DST / 06:00 standard; historical vendor latency not observed")
    else:
        m.update(unit="KRW_per_USD",session_close="Exact fixing/close clock not verified; timestamp labels bar start",
                 availability="Do not assume same-date Korean 09:00 availability; historical publication timestamps unavailable")
    return f[["date","close"]],m


def fred_csv(key, symbol, start, end):
    # Full-history requests timed out; bounded, disjoint annual requests work.
    pieces=[]; responses=[]
    for year in range(int(start[:4]),int(end[:4])+1):
        lower=max(start,f"{year}-01-01"); upper=min(end,f"{year}-12-31")
        for attempt in range(2):
            try:
                response=public_get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                                    params={"id":symbol,"cosd":lower,"coed":upper})
                break
            except requests.RequestException:
                if attempt:raise
        raw_piece=pd.read_csv(io.StringIO(response.text),na_values=["."])
        if list(raw_piece.columns)!=["observation_date",symbol]:
            raise ValueError("Unexpected FRED CSV schema")
        if not raw_piece.empty and not raw_piece.observation_date.between(lower,upper).all():
            raise ValueError("FRED returned dates outside annual request")
        pieces.append(raw_piece)
        responses.append({"url":response.url,"sha256":hashlib.sha256(response.content).hexdigest()})
        print(key,year,"source rows",len(raw_piece),flush=True)
    raw=pd.concat(pieces,ignore_index=True)
    f,qc = canonicalize(raw.rename(columns={"observation_date":"date",symbol:"close"}),start,end)
    m = {"status":"collected","provider":"FRED public CSV",
         "original_provider":"Federal Reserve Board (H.15)" if key=="US10Y" else "U.S. EIA (spot prices)",
         "symbol":symbol,"source_url":"https://fred.stlouisfed.org/graph/fredgraph.csv",
         "annual_responses":responses,
         "series_page":f"https://fred.stlouisfed.org/series/{symbol}","date_semantics":"observation date, not release date",
         "fetched_at":guard(),"unit":"percent_per_annum" if key=="US10Y" else "USD_per_barrel",
         "timezone":"America/New_York" if key=="US10Y" else "observation clock unverified",
         "session_close":"Not an exchange close; official daily yield" if key=="US10Y" else "WTI Cushing spot price, not NYMEX futures settlement",
         "availability":"Release vintages unavailable; do not shift observation date by only one Korean day and claim availability",
         **qc}
    return f,m


def krx_public_discovery():
    """Public code discovery only. No login, key, cookie import, or pykrx import."""
    guard()
    url="https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    with requests.Session() as session:
        session.trust_env=False
        r=session.post(url,data={"locale":"ko_KR","mktsel":"1","searchText":"","bld":"dbms/comm/finder/finder_equidx"},
                       headers={"User-Agent":"Mozilla/5.0","Referer":"https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"},
                       timeout=(10,30),allow_redirects=False)
        r.raise_for_status()
        rows=r.json().get("block1",[])
        matches=[x for x in rows if any(s in str(x).lower() for s in ("변동성","vkospi","v-kospi"))]
        return {"public_url":url,"bld":"dbms/comm/finder/finder_equidx","rows":len(rows),
                "matching_rows":matches,"http_status":r.status_code,"response_sha256":hashlib.sha256(r.content).hexdigest()}


def existing_data():
    states={p.name:state(p) for p in (OPERATING,LONG_PRICE)}
    c=ro(OPERATING)
    try:
        c.execute("BEGIN")
        fx=pd.read_sql_query("SELECT date,close FROM market_daily WHERE series='USDKRW' ORDER BY date",c)
        kr_new=[x[0] for x in c.execute("SELECT date FROM market_daily WHERE series='KOSPI' ORDER BY date")]
        c.rollback()
    finally:c.close()
    c=ro(LONG_PRICE)
    try:
        c.execute("BEGIN")
        names=[x[0] for x in c.execute("SELECT DISTINCT series FROM index_daily")]
        if "KOSPI" not in names:
            raise ValueError("KOSPI calendar not found in index_daily")
        kr_old=[x[0] for x in c.execute("SELECT date FROM index_daily WHERE series='KOSPI' ORDER BY date")]
        c.rollback()
    finally:c.close()
    calendar=sorted(set(kr_old)|set(kr_new))
    assert calendar and len(calendar)==len(set(calendar))
    assert states=={p.name:state(p) for p in (OPERATING,LONG_PRICE)}
    return fx,calendar,states


def fx_comparison(frame, operating, mapping=None):
    f=frame.copy()
    if mapping is not None:
        f["date"]=f.date.map(mapping)
    assert not f.date.duplicated().any()
    joined=f.merge(operating,on="date",suffixes=("_new","_operating"),validate="one_to_one")
    joined=joined[joined.close_operating!=0].copy()
    joined["relative_error"]=(joined.close_new-joined.close_operating).abs()/joined.close_operating.abs()
    matched=int((joined.relative_error<=.001).sum())
    return {"n_overlap":len(joined),"n_within_0_1pct":matched,
            "match_percent":100*matched/len(joined) if len(joined) else None,
            "max_relative_error_percent":float(joined.relative_error.max()*100) if len(joined) else None,
            "mismatch_examples":joined[joined.relative_error>.001].sort_values("relative_error",ascending=False).head(10).to_dict("records")}


def calendar_check(key, frame, calendar):
    dates=frame.date.tolist(); s=set(dates)
    subset=[d for d in calendar if dates[0]<=d<=dates[-1]]; kr=set(subset)
    weekends=sum(datetime.strptime(d,"%Y%m%d").weekday()>=5 for d in dates)
    result={"observations":len(dates),"same_date_on_korean_axis":len(s&kr),
            "source_dates_off_korean_axis":len(s-kr),"source_weekend_dates":weekends,
            "korean_dates_without_same_date_observation":len(kr-s),
            "off_axis_examples":sorted(s-kr)[:12]}
    if key not in ("SPX","IXIC"):
        result["order_mapping"]="not assigned: release timing/vintage unverified"
        return result
    mapped=[]; examples=[]; gaps=[]; missing=0
    for d in dates:
        close=datetime.strptime(d,"%Y%m%d").replace(hour=16,tzinfo=ZoneInfo("America/New_York"))
        available=close.astimezone(ZoneInfo("Asia/Seoul"))
        k=bisect_right(calendar,d)
        while k<len(calendar):
            order=datetime.strptime(calendar[k],"%Y%m%d").replace(hour=9,tzinfo=ZoneInfo("Asia/Seoul"))
            if order>available:break
            k+=1
        if k==len(calendar):missing+=1;continue
        mapped.append(calendar[k])
        gap=(datetime.strptime(calendar[k],"%Y%m%d")-datetime.strptime(d,"%Y%m%d")).days
        gaps.append(gap)
        if len(examples)<12 and (gap>1 or d.endswith("0102")):
            examples.append([d,available.isoformat(),calendar[k],gap])
    result.update(order_mapping="first Korean 09:00 after US 16:00 ET, modelled close not measured publication",
                  mapped_rows=len(mapped),unmapped_after_calendar_end=missing,unique_korean_order_dates=len(set(mapped)),
                  excess_us_rows_sharing_korean_order_date=len(mapped)-len(set(mapped)),
                  calendar_gap_gt1=sum(g>1 for g in gaps),gap_histogram={str(g):gaps.count(g) for g in sorted(set(gaps))},
                  mapping_examples=examples)
    return result


def quality(frames,metadata,fx,calendar):
    result={"series":{},"anomalies":[],"calendar":{}}
    for key,f in frames.items():
        dates=f.date.to_numpy(); vals=f.close.to_numpy(float)
        result["series"][key]={"rows":len(f),"first":dates[0],"last":dates[-1],
                               "duplicate_dates":int(f.date.duplicated().sum()),
                               "descending_dates":int((dates[1:]<dates[:-1]).sum()),
                               "zero_values":int((vals==0).sum()),"negative_values":int((vals<0).sum()),
                               "minimum":float(vals.min()),"maximum":float(vals.max())}
        for i,v in enumerate(vals):
            tags=[]; change=None
            if v==0:tags.append("zero")
            if v<0:tags.append("negative")
            if i and vals[i-1]!=0:
                change=(v-vals[i-1])/abs(vals[i-1])*100
                if abs(change)>10:tags.append("abs_daily_change_gt10pct")
            elif i:tags.append("previous_zero_change_undefined")
            if tags:
                result["anomalies"].append({"series":key,"date":str(dates[i]),"previous_date":str(dates[i-1]) if i else None,
                    "previous_value":float(vals[i-1]) if i else None,"value":float(v),"change_percent":change,"flags":tags})
        if key in ("SPX","IXIC","US10Y","WTI"):
            result["calendar"][key]=calendar_check(key,f,calendar)
    if "USDKRW" in frames:
        result["fx_same_canonical_date"]=fx_comparison(frames["USDKRW"],fx)
        result["fx_legacy_fdr_utc_date"]=fx_comparison(frames["USDKRW"],fx,metadata["USDKRW"]["fdr_date_map"])
    return result


def self_check():
    f,q=canonicalize(pd.DataFrame({"date":["2020-01-01","2020-01-02","2020-01-03"],"close":[1,np.nan,-2]}),"2020-01-01","2020-01-03")
    assert len(f)==2 and f.close.iloc[-1]==-2 and q["missing_source_values_omitted"]==1
    try:canonicalize(pd.DataFrame({"date":["2020-01-01"]*2,"close":[1,1]}),"2020-01-01","2020-01-03")
    except ValueError:pass
    else:raise AssertionError("duplicate source date accepted")
    # London summer bar starts on previous UTC date; winter does not.
    t=pd.DatetimeIndex(["2026-07-01 23:00:00+00:00","2026-01-02 00:00:00+00:00"])
    assert t.tz_convert("Europe/London").strftime("%Y%m%d").tolist()==["20260702","20260102"]
    f=pd.DataFrame({"date":["20260702","20260703"],"close":[100.,101.]})
    z=calendar_check("SPX",f,["20260702","20260703","20260706"])
    assert z["mapped_rows"]==2 and z["gap_histogram"]=={"1":1,"3":1}
    assert calendar_check("US10Y",f,["20260702","20260703","20260706"])["order_mapping"].startswith("not assigned")
    same=fx_comparison(pd.DataFrame({"date":["20260102"],"close":[100.05]}),pd.DataFrame({"date":["20260102"],"close":[100.]}))
    assert same["n_within_0_1pct"]==1
    with sqlite3.connect(":memory:") as c:
        c.executescript(DDL)
        c.execute("INSERT INTO series_daily VALUES ('WTI','20200420',-36.98,'test','test')")
        assert c.execute("SELECT close FROM series_daily").fetchone()[0]<0
    return "PASS: no forward fill; negative values preserved; duplicates rejected; London DST dates; US close/Korean order alignment; unpublished-rate mapping blocked; ±0.1% comparison; schema"


def save_new(frames,metadata,run,qc):
    guard()
    expected=(ROOT.parent/"dh-q7m3k-data"/"macro_10y.db").resolve()
    assert TARGET.resolve()==expected and TARGET.name=="macro_10y.db"
    TARGET.touch(exist_ok=False)
    c=sqlite3.connect(TARGET.as_uri()+"?mode=rw",uri=True)
    try:
        c.execute("PRAGMA journal_mode=DELETE")
        c.executescript("BEGIN IMMEDIATE;\n"+DDL)
        for key,f in frames.items():
            meta=metadata[key]
            source=meta["provider"]+":"+meta["symbol"]
            c.executemany("INSERT INTO series_daily VALUES (?,?,?,?,?)",[(key,d,float(v),source,meta["fetched_at"]) for d,v in f.itertuples(index=False,name=None)])
        objects={"run":run,"quality_at_collection":qc,**{f"series:{key}":value for key,value in metadata.items()}}
        c.executemany("INSERT INTO meta VALUES (?,?)",[(key,json.dumps(value,ensure_ascii=False,allow_nan=False)) for key,value in objects.items()])
        guard();c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()
    c=ro(TARGET)
    try:assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    finally:c.close()


def read_collected():
    c=ro(TARGET)
    try:
        assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        allrows=pd.read_sql_query("SELECT series,date,close FROM series_daily ORDER BY series,date",c)
        meta={k:json.loads(v) for k,v in c.execute("SELECT key,value FROM meta")}
    finally:c.close()
    frames={key:f[["date","close"]].reset_index(drop=True) for key,f in allrows.groupby("series",sort=False)}
    return frames,{key:meta[f"series:{key}"] for key in ORDER},meta["run"]


def collect(start,end):
    if TARGET.exists():raise FileExistsError("Existing macro_10y.db will not be overwritten; use --check")
    run={"started_at":guard(),"request":"REQUEST_20261101_macro_10y_fetch","start":start,"end":end,
         "code_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"python":sys.version.split()[0],
         "pandas":pd.__version__,"network_authorized_by_request":True,"no_authentication":True,"no_fill":True}
    frames={};metadata={}
    jobs=[("USDKRW",lambda:yahoo_fdr("USDKRW","USD/KRW",start,end)),
          ("SPX",lambda:yahoo_fdr("SPX","US500",start,end)),
          ("IXIC",lambda:yahoo_fdr("IXIC","IXIC",start,end)),
          ("US10Y",lambda:fred_csv("US10Y","DGS10",start,end)),
          ("WTI",lambda:fred_csv("WTI","DCOILWTICO",start,end)),
          ("VKOSPI",lambda:yahoo_fdr("VKOSPI","VKOSPI",start,end))]
    for key,job in jobs:
        print(f"fetch {key}",flush=True)
        try:
            frames[key],metadata[key]=job()
            print(key,len(frames[key]),frames[key].date.min(),frames[key].date.max(),flush=True)
        except (requests.RequestException,ValueError,KeyError,IndexError,TypeError) as exc:
            metadata[key]={"status":"unavailable","reason":type(exc).__name__+": "+str(exc)[:240],"fetched_at":guard()}
            print(key,"unavailable",type(exc).__name__,flush=True)
    if metadata["VKOSPI"]["status"]!="collected":
        try:metadata["VKOSPI"]["public_discovery"]=krx_public_discovery()
        except (requests.RequestException,ValueError) as exc:metadata["VKOSPI"]["public_discovery_error"]=type(exc).__name__
        metadata["VKOSPI"]["limitation"]="FDR has no VKOSPI alias; no verified public historical series acquired. Did not import pykrx or attempt authenticated KRX routes."
    metadata["KR3Y"]={"status":"not_collected_optional","reason":"No public keyless daily Korean 3-year government yield route verified. ECOS credentials not read or used; no monthly/interbank substitute.","fetched_at":guard()}
    fx,calendar,states=existing_data()
    run.update(existing_db_states=states,korean_calendar={"first":calendar[0],"last":calendar[-1],"rows":len(calendar),"sources":["ohlcv_10y.db:index_daily KOSPI","ohlcv.db:market_daily KOSPI"]})
    qc=quality(frames,metadata,fx,calendar)
    assert states=={p.name:state(p) for p in (OPERATING,LONG_PRICE)}
    run["finished_at"]=guard()
    save_new(frames,metadata,run,qc)
    return frames,metadata,run,qc


def complete_missing():
    """Fill only failed FRED series in this collector's own new macro database.

    No existing series rows are updated/deleted and no other DB can be written.
    All responses and checks succeed before the single insert transaction.
    """
    frames,metadata,run=read_collected()
    if run.get("request")!="REQUEST_20261101_macro_10y_fetch" or not run.get("no_authentication"):
        raise ValueError("Not this collector's macro database")
    pending=[(key,symbol) for key,symbol in (("US10Y","DGS10"),("WTI","DCOILWTICO"))
             if key not in frames and metadata[key]["status"]=="unavailable"]
    if not pending:raise ValueError("No failed FRED series to complete")
    fx,calendar,states=existing_data()
    if states!=run["existing_db_states"]:raise RuntimeError("Existing comparison DB changed")
    prior={key:metadata[key] for key,_ in pending}
    for key,symbol in pending:
        frames[key],metadata[key]=fred_csv(key,symbol,run["start"],run["end"])
    qc=quality(frames,metadata,fx,calendar)
    run["completion_attempt"]={"initial_finished_at":run["finished_at"],"prior_failures":prior,
                               "initial_code_sha256":run["code_sha256"]}
    run["code_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    run["finished_at"]=guard()
    assert states=={p.name:state(p) for p in (OPERATING,LONG_PRICE)}
    assert TARGET.resolve()==(DATA/"macro_10y.db").resolve()
    c=sqlite3.connect(TARGET.as_uri()+"?mode=rw",uri=True)
    try:
        c.execute("BEGIN IMMEDIATE")
        for key,_ in pending:
            if c.execute("SELECT count(*) FROM series_daily WHERE series=?",(key,)).fetchone()[0]:
                raise RuntimeError("Series already populated; no overwrite allowed")
            m=metadata[key]
            c.executemany("INSERT INTO series_daily VALUES (?,?,?,?,?)",
                          [(key,d,float(v),m["provider"]+":"+m["symbol"],m["fetched_at"])
                           for d,v in frames[key].itertuples(index=False,name=None)])
        objects={"run":run,"quality_at_collection":qc,**{f"series:{k}":metadata[k] for k,_ in pending}}
        for key,value in objects.items():
            c.execute("UPDATE meta SET value=? WHERE key=?",(json.dumps(value,ensure_ascii=False,allow_nan=False),key))
        guard();c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()
    read_collected()  # Read-only integrity check after commit.
    return frames,metadata,run,qc


def fmt(x,n=3):
    return "NA" if x is None else f"{x:.{n}f}"


def report_text(frames,metadata,run,qc):
    lines=["# REPLY — 바깥 시계열 수집·품질 검사 (20261101 요청)","",
           f"수집 구간은 **{run['start']}~{run['end']}**로 고정했다. 실행 {run['started_at']}~{run['finished_at']}. 새 DB `{TARGET}`에만 데이터를 기록했다. 기존 두 DB는 mode=ro/query_only였다. 배치 연결·모델 분석·전략 수익률 계산은 하지 않았다.","",
           "## 1. 시리즈별 범위·출처","",
           "|키|상태|행|첫 날짜|끝 날짜|출처/심볼|단위|", "|---|---|---:|---|---|---|---|"]
    for key in ORDER:
        m=metadata[key];s=qc["series"].get(key)
        if s:lines.append(f"|{key}|수집|{s['rows']}|{s['first']}|{s['last']}|{m['provider']} / {m['symbol']}|{m['unit']}|")
        else:lines.append(f"|{key}|확인 못 함/생략|0|—|—|{m.get('reason','')}|—|")
    lines += ["", "IXIC는 나스닥 종합지수다. NDX(나스닥100)와 동일하지 않으며 요청의 'NDX 또는 IXIC' 중 IXIC를 선택했다. US10Y는 지수 가격이 아닌 연율 % 금리(예: 4.98)를 그대로 저장했다. WTI는 EIA 원자료의 Cushing 현물가격을 FRED 공개 CSV로 받았으며 선물 결제가격으로 대체하지 않았다.","",
              "VKOSPI는 설치 FDR의 전용 심볼 매핑이 없었다. 공개 Yahoo 심볼 시도와 KRX 공개 지수 검색만 수행했고, 확인된 역사 시계열을 얻지 못했다. pykrx import/로그인·.env·키 조회는 하지 않았다. 대안은 사용자가 공식 KRX 일별 자료를 직접 내려받아 별도 검증 뒤 가져오는 방법이다. VIX를 VKOSPI 이름으로 넣거나 계산한 변동성으로 대체하지 않았다. KR3Y는 키 없는 일별 국고 3년 경로를 확인하지 못해 선택 항목으로 생략했다.","",
              "## 2. 결측·중복·날짜 순서 검사","",
              "소스의 결측값은 행을 저장하지 않았고 휴장일을 생성하지 않았다. 설치 FDR의 FRED reader는 ffill을 수행하므로 사용하지 않고 원본 CSV를 직접 파싱했다. 음수나 극단값은 자동 삭제·절단하지 않았다.","",
              "|키|원본 결측 값 제외|원본 중복|원본 내림차순 구간|저장 중복|저장 역행|0 값|음수|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key,s in qc["series"].items():
        m=metadata[key]
        lines.append(f"|{key}|{m['missing_source_values_omitted']}|{m['source_duplicate_dates']}|{m['source_descending_steps_before_sort']}|{s['duplicate_dates']}|{s['descending_dates']}|{s['zero_values']}|{s['negative_values']}|")
    lines += ["", "SQLite PK(series,date), 날짜 형식 제약, integrity_check=ok를 확인했다. 빈값을 0이나 직전 값으로 바꾸지 않았다. 저장 정렬 검사는 ORDER BY date로 읽은 결과이며 원본의 정렬 상태는 위 별도 열이다.","",
              "## 3. USDKRW 운영 DB 대조 (허용 오차 ±0.1%)","",
              "|대조 기준|겹침 날짜|±0.1% 안|일치율 %|최대 상대 오차 %|", "|---|---:|---:|---:|---:|"]
    for label,key in [("새 DB 현지 일봉 날짜 그대로","fx_same_canonical_date"),("검사에서만 기존 FDR UTC 날짜로 대응","fx_legacy_fdr_utc_date")]:
        x=qc.get(key)
        if x:lines.append(f"|{label}|{x['n_overlap']}|{x['n_within_0_1pct']}|{fmt(x['match_percent'])}|{fmt(x['max_relative_error_percent'])}|")
    if "USDKRW" in frames:
        m=metadata["USDKRW"]
        lines += ["",f"Yahoo 응답 timezone={m['timezone']}. 설치 FDR은 UTC timestamp를 바로 날짜로 잘라 쓰며, 제공처 현지 날짜와 다른 행이 전체 수집 구간에서 {m['fdr_utc_label_changes']}개였다. 새 DB는 제공처 시간대의 날짜를 썼다. 두 번째 줄은 동일 응답의 값들을 기존 FDR 날짜에 대응시킨 품질 진단일 뿐, 저장 날짜를 운영 DB에 맞추어 고치거나 기존 DB를 수정한 것이 아니다.","",
                  "현지 날짜 기준 불일치 예시(상대 오차 큰 10건):", "",
                  "|날짜|새 DB|운영 DB|상대 오차 %|", "|---|---:|---:|---:|"]
        for x in qc["fx_same_canonical_date"]["mismatch_examples"]:
            lines.append(f"|{x['date']}|{fmt(x['close_new'],6)}|{fmt(x['close_operating'],6)}|{fmt(x['relative_error']*100)}|")
        legacy=qc["fx_legacy_fdr_utc_date"]
        lines += ["",f"기존 FDR 날짜로 대응해도 {legacy['n_overlap']-legacy['n_within_0_1pct']}건은 허용 오차 밖이다. 날짜 처리만으로 모든 차이가 설명되지는 않는다. 값의 수정·수집 시점 차이 등 잔여 원인은 확인 못 했으며, 원자료를 운영 DB 값으로 덮어 맞추지 않았다."]
    lines += ["", "## 4. 극단값·0·음수 목록","",
              "연속 관측값 사이의 `100×(현재−이전)/abs(이전)` 절댓값 >10% 또는 값 0/음수를 표시한다. 휴장으로 관측 사이 날짜가 벌어질 수 있다. 이는 요청된 품질 검사이며 투자 수익률 분석이 아니다. 금리의 작은 분모와 유가의 음수는 자동 오류로 단정하지 않는다.","",
              "|시리즈|이전 날짜|날짜|이전 값|값|변화율 %|표시|", "|---|---|---|---:|---:|---:|---|"]
    if not qc["anomalies"]:lines.append("|없음|—|—|—|—|—|—|")
    for x in qc["anomalies"]:
        lines.append(f"|{x['series']}|{x['previous_date']}|{x['date']}|{fmt(x['previous_value'],6)}|{fmt(x['value'],6)}|{fmt(x['change_percent'])}|{','.join(x['flags'])}|")
    lines += ["", "## 5. 미국 날짜와 한국 거래일 축","",
              f"한국 달력은 두 기존 DB의 KOSPI 날짜 합집합 {run['korean_calendar']['rows']}일({run['korean_calendar']['first']}~{run['korean_calendar']['last']})이다. 분석 가격을 가져오거나 새 수익률을 계산하지 않고 날짜만 사용했다.","",
              "|시리즈|관측 행|같은 날짜가 한국 거래일|한국 축 밖 미국 날짜|그중 주말|한국 거래일인데 같은 날짜 관측 없음|", "|---|---:|---:|---:|---:|---:|"]
    for key,x in qc["calendar"].items():
        lines.append(f"|{key}|{x['observations']}|{x['same_date_on_korean_axis']}|{x['source_dates_off_korean_axis']}|{x['source_weekend_dates']}|{x['korean_dates_without_same_date_observation']}|")
    lines += ["", "SPX/IXIC 연결 규칙: 원 미국 날짜 D를 보존하고, 정규장 종가를 D 16:00 America/New_York로 놓은 뒤 그 시각보다 늦은 첫 한국 거래일 09:00에 대응한다. 서머타임에 한국 다음 달력일 05:00, 표준시에 06:00다. 조기 폐장은 더 이르므로 16:00 가정이 보수적이다. 여러 미국 관측이 같은 한국 개장에 대응하면 나중 분석에서 공개 시각이 가장 늦은 하나를 골라야 하며 평균을 내거나 원표를 채우지 않는다. 이는 장 마감 시각 기준 규칙으로 실제 데이터 제공처의 과거 게시 지연을 확인한 것은 아니다.","",
              "|시리즈|다음 한국 개장에 대응|한국 달력 끝 이후 미대응|대응 한국 날짜 수|같은 한국 날짜로 모이는 추가 미국 행|날짜 간격>1일|", "|---|---:|---:|---:|---:|---:|"]
    for key in ("SPX","IXIC"):
        x=qc["calendar"].get(key)
        if x:lines.append(f"|{key}|{x['mapped_rows']}|{x['unmapped_after_calendar_end']}|{x['unique_korean_order_dates']}|{x['excess_us_rows_sharing_korean_order_date']}|{x['calendar_gap_gt1']}|")
    lines += ["", "실제 달력 대응 예시(휴일/주말 포함):", "", "|시리즈|미국 날짜|16시 종가의 한국 시각|대응 한국 날짜|달력일 간격|", "|---|---|---|---|---:|"]
    for key in ("SPX","IXIC"):
        for d,t,k,g in qc["calendar"].get(key,{}).get("mapping_examples",[]):
            lines.append(f"|{key}|{d}|{t}|{k}|{g}|")
    lines += ["", "**US10Y와 WTI에는 같은 1일 이동 규칙을 적용하지 않았다.** 관측일은 공개일이 아니다. H.15는 미국 업무일 16:15 공표지만 확인한 2026-10-30 공개 표는 10/29까지 담고 있고, FRED도 관측 10/29를 10/30에 갱신했다. WTI도 확인한 최신 관측 10/27과 갱신 10/28이 다르며 다음 공개 일정이 11/4였다. 과거 각 날짜의 공개 시각/vintage가 없는 현재 CSV로 '한국 다음 거래일 주문 전에 모두 알려짐'을 주장할 수 없다. 이 두 시리즈의 주문일 매핑은 미확인으로 남기고, 나중 분석 전에 공표일 자료 또는 사전 고정한 보수적 지연을 별도로 확보해야 한다.",
              "USDKRW 역시 일봉 시각이 해당 봉의 시작 라벨이므로 정확한 종가/fixing 시각과 당시 공개 여부는 확인 못 했다. 한국 같은 날짜 오전에 그날 최종 환율을 쓸 수 있다고 간주하지 않는다.","",
              "출처: [NYSE 정규장 시간](https://www.nyse.com/trade/trading-information), [Nasdaq 거래시간](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule), [Federal Reserve H.15](https://www.federalreserve.gov/releases/h15/), [FRED DGS10](https://fred.stlouisfed.org/series/DGS10), [FRED EIA WTI](https://fred.stlouisfed.org/series/DCOILWTICO). 공개 페이지 확인 시점은 이 수집 작업 중이며 과거 공개 시각 전수 검증이 아니다.","",
              "## 6. 저장 구조·재현·한계","",
              "`series_daily(series,date,close,source,fetched_at)`의 PK는 `(series,date)`. `meta(key,value)`에는 요청 기간·소스 URL/심볼·응답 SHA256·단위·시간대·FDR 날짜 대응·수집 실패 이유·품질 검사 JSON을 저장했다. 새 DB의 파일명만 10y이며 요청 기간은 2015년부터다.","",
              "재현(새 대상 파일이 없을 때만):", "",f"`python -X utf8 -B research/fetch_macro_10y.py --collect --start {run['start']} --end {run['end']} --write-report`", "",
              "수집 없이 기존 결과 재검사: `python -X utf8 -B research/fetch_macro_10y.py --check --write-report`.",
              "자체 점검: `python -X utf8 -B research/fetch_macro_10y.py --self-check`.","",
              "기존 macro_10y.db가 있으면 --collect는 덮어쓰기를 거부한다. --check는 모든 DB를 읽기만 하며 새 네트워크 호출을 하지 않는다. 별도 --write-report를 명시한 경우에만 이 답 파일을 갱신한다. 월~금 20:10~22:30 KST에는 조회/저장을 거부한다.","",
              f"수집 코드 SHA256 `{run['code_sha256']}`. Python {run['python']}, pandas {run['pandas']}. 수집한 값은 현재 제공처의 역사 스냅샷이며 과거 수정 전 값의 보관본이 아니다. 결측·휴장·마지막 게시일 차이를 메우지 않았고, 운영 DB의 환율 날짜/값도 수정하지 않았다.","",
              "|읽은 기존 DB|크기 bytes|mtime_ns 전=후|", "|---|---:|---:|"]
    lines += [f"|{key}|{v[0]}|{v[1]}|" for key,v in run["existing_db_states"].items()]
    lines += ["", "크기/수정 시각 비교는 파일 내용 해시 검증과는 다르다. 데이터 기록은 새 macro_10y.db에 한정했다. 배치·점수·모델·기존 DB 변경 없음. 외부 API 응답 임시 파일도 따로 남기지 않았다.",""]
    if "completion_attempt" in run:
        lines += ["미국 금리·유가는 첫 전체 기간 요청에서 시간 초과/연결 실패가 발생했다. 연도별 공개 CSV로 다시 받아 이번 작업에서 만든 macro_10y.db의 비어 있던 두 시리즈만 보완했다. 먼저 수집한 세 시리즈는 덮어쓰지 않았다. 실패 기록과 최초 코드 해시는 meta.run.completion_attempt에 보존했다.","",
                  "중단된 같은 수집의 FRED 누락분 보완 명령은 `python -X utf8 -B research/fetch_macro_10y.py --complete-missing --write-report`다. 해당 요청의 메타정보와 기존 비교 DB 상태를 검사하고, 이미 있는 시리즈는 수정하지 않으며 보완할 항목이 없으면 종료한다.",""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect",action="store_true")
    mode.add_argument("--check",action="store_true")
    mode.add_argument("--complete-missing",action="store_true")
    mode.add_argument("--self-check",action="store_true")
    parser.add_argument("--start",default="2015-01-01")
    parser.add_argument("--end",default=(datetime.now(ZoneInfo("Asia/Seoul")).date()-timedelta(days=1)).isoformat())
    parser.add_argument("--write-report",action="store_true")
    args=parser.parse_args();guard()
    print(self_check(),flush=True)
    if args.self_check:return
    if args.collect:
        if pd.Timestamp(args.start)>pd.Timestamp(args.end):raise ValueError("start>end")
        if pd.Timestamp(args.end).date()>=datetime.now(ZoneInfo("Asia/Seoul")).date():raise ValueError("end must precede current KST date")
        frames,metadata,run,qc=collect(args.start,args.end)
    elif args.complete_missing:
        frames,metadata,run,qc=complete_missing()
    else:
        frames,metadata,run=read_collected()
        fx,calendar,current_states=existing_data()
        qc=quality(frames,metadata,fx,calendar)
        if current_states!=run["existing_db_states"]:
            raise RuntimeError("Comparison databases changed since collection; keep original report, investigate before replacing")
    report=report_text(frames,metadata,run,qc)
    if args.write_report:
        guard();REPLY.write_text(report,encoding="utf-8")
        print("REPORT",REPLY,flush=True)
        print("DB",TARGET,"rows",sum(len(f) for f in frames.values()),"bytes",TARGET.stat().st_size,flush=True)
        print("FX",json.dumps({k:qc.get(k) for k in ("fx_same_canonical_date","fx_legacy_fdr_utc_date")},ensure_ascii=False),flush=True)
    else:print(report)


if __name__=="__main__":main()
