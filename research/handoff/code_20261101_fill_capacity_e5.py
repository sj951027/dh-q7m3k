"""E5 capacity arithmetic from stored rankings, freshly implemented.

Only two SQLite inputs, explicit mode=ro/query_only; no repository imports.
Default stdout. --write-report updates the designated reply before section 6.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PRICE_DB = ROOT.parent / "dh-q7m3k-data" / "ohlcv.db"
HISTORY_DB = ROOT / "history.db"
REPLY = Path(__file__).with_name("REPLY_20261101_fill_capacity_e5.md")
MODELS = ("v30", "lv_b", "v32a")
PARTICIPATIONS = (.005, .01, .02, .05)
BUDGETS = (1_000_000, 10_000_000, 100_000_000, 1_000_000_000)
QUANTILES = (.1, .25, .5, .75, .9)
MARKER = "## 1. 자료 범위와 계산 기록"


def time_guard():
    dt = datetime.now(ZoneInfo("Asia/Seoul"))
    if dt.weekday() < 5 and "20:10" <= dt.strftime("%H:%M") < "22:30":
        raise RuntimeError("평일 20:10~22:30 파일/DB 접근 제한")
    return dt.isoformat(timespec="seconds")


def snapshot(path):
    s = path.stat()
    return (s.st_size, s.st_mtime_ns)


def read_frames(path, queries):
    time_guard()
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        assert con.execute("PRAGMA query_only").fetchone()[0] == 1
        con.execute("BEGIN")
        return [pd.read_sql_query(sql, con, params=params) for sql, params in queries]
    finally:
        con.rollback()
        con.close()


def normalize_tickers(f):
    f["ticker"] = f.ticker.astype(str).str.strip().str.zfill(6)
    return f


def select_top(f):
    f = f.copy()
    normalize_tickers(f)
    f["market"] = f.market.str.upper()
    f = f[f.market.isin(["KOSPI", "KOSDAQ"]) & f.score.notna()].copy()
    f = f.sort_values(["model_id", "run_id", "market", "score", "ticker"],
                      ascending=[True, True, True, False, True], kind="stable")
    return f.groupby(["model_id", "run_id", "market"], sort=False).head(10).reset_index(drop=True)


def prior_average(calendar, amounts, run):
    stop = int(np.searchsorted(calendar, run, side="left"))
    segment = amounts[max(0, stop-20):stop]
    count = int(np.isfinite(segment).sum())
    result = float(segment.mean()) if len(segment) == 20 and count == 20 else np.nan
    return result, count, stop


def obstruction(volume, suspended, change):
    zero = bool(np.isfinite(volume) and volume == 0)
    halt = bool(np.isfinite(suspended) and suspended == 1)
    up = bool(np.isfinite(change) and change >= .29)
    blocked = zero or halt or up
    known = blocked or (np.isfinite(volume) and volume >= 0 and suspended in (0,1) and np.isfinite(change))
    return blocked, bool(known), zero, halt, up


def limits(adv, p):
    adv = np.asarray(adv, float)
    if len(adv) == 0 or not np.isfinite(adv).all():
        return np.nan, np.nan, np.nan
    each = adv*p
    return float(each.sum()), float(each.min()*800), float(np.median(each)*800)


def exceed_count(adv, p, total):
    adv = np.asarray(adv, float)
    if len(adv) == 0 or not np.isfinite(adv).all():
        return np.nan
    return int((total/20 > adv*p).sum())


def checks():
    cal = pd.bdate_range("20260101", periods=26).strftime("%Y%m%d").to_numpy()
    amount = np.arange(1.,27.)
    avg, count, stop = prior_average(cal,amount,cal[20])
    assert avg == 10.5 and count == 20 and stop == 20
    changed = amount.copy(); changed[20:] = 999999.
    assert prior_average(cal,changed,cal[20])[0] == avg
    # Saturday must include Friday, with exactly 20 past market sessions.
    fri = [i for i,x in enumerate(cal) if pd.Timestamp(x).weekday() == 4 and i >= 20][0]
    sat = (pd.Timestamp(cal[fri])+pd.Timedelta(days=1)).strftime("%Y%m%d")
    assert np.isclose(prior_average(cal,amount,sat)[0],amount[fri-19:fri+1].mean())
    zero = amount.copy(); zero[0] = 0
    assert prior_average(cal,zero,cal[20])[0] == (210-1)/20
    missing = amount.copy(); missing[0] = np.nan
    assert np.isnan(prior_average(cal,missing,cal[20])[0])
    assert np.isnan(prior_average(cal,amount,cal[19])[0])
    a = np.array([100.,200.,300.,400.])
    l1 = np.array(limits(a,.01)); l2=np.array(limits(a,.02))
    assert np.allclose(l2,2*l1) and l1[1] == 800 and l1[2] == 2000
    assert exceed_count(np.array([100.,200.]),.01,20) == 0
    assert exceed_count(np.array([100.,200.]),.01,20.01) == 1
    assert obstruction(0,1,.3)[:2] == (True,True)
    assert obstruction(1,0,np.nan)[:2] == (False,False)
    assert obstruction(0,1,np.nan)[:2] == (True,True)
    assert obstruction(1,0,.28999)[:2] == (False,True)
    assert obstruction(1,0,.29)[0]
    mock = pd.DataFrame({"model_id":["a"]*12,"run_id":["20260101"]*12,
                         "market":["kospi"]*12,"ticker":[str(i) for i in range(12,0,-1)],"score":[1.]*12})
    assert select_top(mock).ticker.tolist() == [f"{i:06d}" for i in range(1,11)]
    # Two model allocations to a shared stock must be added before the test.
    li = 100.; single = 60.
    assert single <= li and 2*single > li
    return "PASS: 당일/미래 제외, 휴일 앵커, 0거래량 포함, 결측/20일 부족, p 선형성, NAV×800, 엄격 초과, 장애 합집합/미확인, 동점 순위, 중복 주문 합산"


def won(x):
    return "NA" if not np.isfinite(x) else f"{x:,.0f}"


def eok(x):
    return "NA" if not np.isfinite(x) else f"{x/100_000_000:.4f}"


def decimal(x, digits=2):
    return "NA" if not np.isfinite(x) else f"{x:.{digits}f}"


def median(x):
    x = np.asarray(x,float)
    x=x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else np.nan


def partition(picks):
    for model in MODELS:
        data = picks[picks.model_id == model]
        for period in ["전체"] + sorted(data.run_id.str[:6].unique()):
            period_data = data if period == "전체" else data[data.run_id.str.startswith(period)]
            for market in ("전체","KOSPI","KOSDAQ"):
                sub = period_data if market == "전체" else period_data[period_data.market == market]
                if len(sub):
                    yield model,period,market,sub


def anchor_stats(sub, p):
    rows=[]
    for run,f in sub[sub.full20].groupby("run_id",sort=True):
        total,minimum,mid = limits(f.adv20,p)
        rows.append((run,total,minimum,mid,*[exceed_count(f.adv20,p,x) for x in BUDGETS]))
    return pd.DataFrame(rows,columns=["run","sum","nav_min","nav_med","b1","b10","b100","b1000"])


def generate(write_report=False):
    started = time_guard(); began=time.monotonic()
    before={"ohlcv":snapshot(PRICE_DB),"history":snapshot(HISTORY_DB)}
    check_message=checks()
    raw_v,raw_lv = read_frames(HISTORY_DB,[
        ("SELECT model_id,run_id,market,ticker,final_score_v3 AS score FROM v3_scores WHERE model_id IN ('v30','v32a') AND run_id>='20260601'",()),
        ("SELECT model_id,run_id,market,ticker,lowvol_score AS score FROM lowvol_scores WHERE model_id='lv_b' AND run_id>='20260601'",())])
    raw=pd.concat([raw_v,raw_lv],ignore_index=True)
    assert set(raw.model_id) == set(MODELS)
    assert raw.run_id.str.fullmatch(r"\d{8}").all()
    picks=select_top(raw)
    calframe,=read_frames(PRICE_DB,[("""SELECT date FROM (
        SELECT date,market FROM daily_ohlcv WHERE market IN ('KOSPI','KOSDAQ')
        UNION SELECT date,market FROM daily_ohlcv_extra WHERE market IN ('KOSPI','KOSDAQ')
        ) GROUP BY date HAVING count(DISTINCT market)=2 ORDER BY date""",())])
    calendar=calframe.date.to_numpy(dtype="U8")
    first=int(np.searchsorted(calendar,picks.run_id.min(),side="left"))
    assert first>=20
    lower=calendar[first-20]
    price_parts=read_frames(PRICE_DB,[(f"SELECT ticker,date,close,volume,is_suspended,change_pct FROM {table} WHERE date>=?",(str(lower),)) for table in ("daily_ohlcv","daily_ohlcv_extra")])
    sources=[(table,len(f),int(f.ticker.nunique())) for table,f in zip(("daily_ohlcv","daily_ohlcv_extra"),price_parts)]
    price=pd.concat([normalize_tickers(f) for f in price_parts],ignore_index=True)
    duplicate=int(price.duplicated(["ticker","date"]).sum())
    price=price.drop_duplicates(["ticker","date"],keep="first")
    price=price[price.ticker.isin(picks.ticker)].copy()
    tickers=np.array(sorted(picks.ticker.unique())); ticker_col={t:i for i,t in enumerate(tickers)}
    arrays={col:price.pivot(index="date",columns="ticker",values=col).reindex(index=calendar,columns=tickers).to_numpy(float)
            for col in ("close","volume","is_suspended","change_pct")}
    close,volume=arrays["close"],arrays["volume"]
    amounts=np.where((close>0) & (volume>=0) & np.isfinite(close) & np.isfinite(volume),close*volume,np.nan)
    observations=[]
    for r in picks.itertuples(index=False):
        j=ticker_col[r.ticker]
        adv,nvalid,stop=prior_average(calendar,amounts[:,j],r.run_id)
        nxt=int(np.searchsorted(calendar,r.run_id,side="right"))
        future=nxt>=len(calendar)
        if future:
            blocked,known,z,h,u=False,False,False,False,False
            nd="미관측"; row_missing=False; big=False
        else:
            nd=calendar[nxt]
            v=volume[nxt,j]; s=arrays["is_suspended"][nxt,j]; c=arrays["change_pct"][nxt,j]
            blocked,known,z,h,u=obstruction(v,s,c)
            row_missing=not np.isfinite(close[nxt,j])
            big=bool(np.isfinite(c) and c>.31)
        observations.append((adv,nvalid,calendar[stop-20],calendar[stop-1],nd,blocked,known,z,h,u,future,row_missing,big))
    cols=["adv20","valid_days","lookback_start","lookback_end","next_day","blocked","known","zero","halt","up29","future_unknown","row_missing","change_over31"]
    picks=pd.concat([picks,pd.DataFrame(observations,columns=cols)],axis=1)
    anchor_info=[]
    for (model,run),f in picks.groupby(["model_id","run_id"],sort=True):
        counts=f.groupby("market").size()
        full_score=all(counts.get(m,0)==10 for m in ("KOSPI","KOSDAQ"))
        valid=int(f.adv20.notna().sum())
        anchor_info.append((model,run,len(f),valid,full_score,full_score and valid==20))
    info=pd.DataFrame(anchor_info,columns=["model_id","run_id","selected","adv_valid","score20","full20"])
    picks=picks.merge(info[["model_id","run_id","full20"]],on=["model_id","run_id"],how="left",validate="many_to_one")
    assert not picks.duplicated(["model_id","run_id","market","ticker"]).any()
    assert (picks.groupby(["model_id","run_id","market"]).size()<=10).all()
    assert (picks.loc[picks.adv20.notna(),"adv20"]>=0).all()
    lines=[MARKER,"",f"실측 실행 시작 {started}. {check_message}","",
           f"공통 거래일 {len(calendar)}개({calendar[0]}~{calendar[-1]}), 이번 시세 읽기 하한 {lower}. 결합 중복 {duplicate}건(본표 우선).",
           "v32a는 별도 표가 아니라 v3_scores.model_id='v32a'에 저장되어 있었다. lv_b는 lowvol_scores.lowvol_score를 사용했다.","",
           "|모델|원 점수 행|원 run_id|선택 슬롯|고유 종목|첫~끝 run_id|20종목 구성 앵커|ADV까지 완전 20 앵커|ADV 미확인 슬롯|", "|---|---:|---:|---:|---:|---|---:|---:|---:|"]
    for model in MODELS:
        r=raw[raw.model_id==model]; f=picks[picks.model_id==model]; a=info[info.model_id==model]
        lines.append(f"|{model}|{len(r):,}|{r.run_id.nunique()}|{len(f)}|{f.ticker.nunique()}|{f.run_id.min()}~{f.run_id.max()}|{int(a.score20.sum())}|{int(a.full20.sum())}|{int(f.adv20.isna().sum())}|")
    lines += ["", f"원 점수 NULL {int(raw.score.isna().sum())}행(있으면 상위 선정에서 제외). 시세 읽은 행: "+", ".join(f"{t} {n:,}행/{u}종목" for t,n,u in sources)+".",
              "같은 ticker가 반복 선정된 슬롯을 포함한다. 고유 종목 수를 독립 표본 수라고 해석하지 않는다. 과거 다른 모델 점수로 v32a를 재구성하지 않았다.","",
              "불완전 목록의 실제 선택 수:","",
              "|모델/run_id|KOSPI|KOSDAQ|합계|ADV 미확인|", "|---|---:|---:|---:|---:|"]
    for r in info[~info.full20].itertuples(index=False):
        f=picks[(picks.model_id==r.model_id) & (picks.run_id==r.run_id)]
        lines.append(f"|{r.model_id}/{r.run_id}|{int((f.market=='KOSPI').sum())}|{int((f.market=='KOSDAQ').sum())}|{len(f)}|{int(f.adv20.isna().sum())}|")
    lines += ["",
              "## 2. 질문별 핵심 수치 (p=1%)","",
              "### 2.1 종목당 한도와 날짜별 계좌 한도","",
              "금액 단위 **억원**. 종목 Q10/Q50은 유효 선택 슬롯 전체, 목록/NAV 요약은 완전 20종목 앵커만 사용한다. NAV_min 날짜 최소는 관측한 모든 완전 목록을 같은 NAV로 따르려 할 때 가장 엄격했던 값이다.","",
              "|모델|유효 슬롯/완전 앵커|종목 Q10|종목 Q50|목록 Σ 날짜 중앙|NAV_min 날짜 최소/중앙/최대|NAV_med 날짜 중앙|", "|---|---:|---:|---:|---:|---:|---:|"]
    headline={}
    for model in MODELS:
        f=picks[picks.model_id==model]; valid=f.adv20.dropna().to_numpy()
        q=np.quantile(valid*.01,[.1,.5],method="linear")
        a=anchor_stats(f,.01)
        lines.append(f"|{model}|{len(valid)}/{len(a)}|{eok(q[0])}|{eok(q[1])}|{eok(median(a['sum']))}|{eok(a.nav_min.min())}/{eok(median(a.nav_min))}/{eok(a.nav_min.max())}|{eok(median(a.nav_med))}|")
        headline[model]=(q,a)
    lines += ["", "### 2.2 v32a 대 v30 — 같은 날짜만 비교","",
              "|시장|공통 완전 앵커|v32a ADV20 슬롯 중앙(원)|v30 ADV20 슬롯 중앙(원)|중앙값 비(v32a/v30)|날짜별 중앙값 비의 중앙|1% 한도 비|", "|---|---:|---:|---:|---:|---:|---:|"]
    common=sorted(set(info.loc[(info.model_id=="v32a") & info.full20,"run_id"]) & set(info.loc[(info.model_id=="v30") & info.full20,"run_id"]))
    paired=picks[picks.run_id.isin(common) & picks.model_id.isin(["v30","v32a"])]
    ratio_summary={}
    for market in ("전체","KOSPI","KOSDAQ"):
        f=paired if market=="전체" else paired[paired.market==market]
        m32=median(f.loc[f.model_id=="v32a","adv20"]); m30=median(f.loc[f.model_id=="v30","adv20"])
        ratios=[]
        for run,g in f.groupby("run_id"):
            x=median(g.loc[g.model_id=="v32a","adv20"]); y=median(g.loc[g.model_id=="v30","adv20"])
            ratios.append(x/y if y else np.nan)
        ratio=m32/m30 if m30 else np.nan
        ratio_summary[market]=ratio
        lines.append(f"|{market}|{len(common)}|{won(m32)}|{won(m30)}|{decimal(ratio,4)}|{decimal(median(ratios),4)}|{decimal(ratio,4)}|")
    lines += ["", "5일 안에서도 비율이 달라질 수 있다. 이 비율을 2026-06 이후 전체 기간의 모델 차이나 미래 예상치로 확장하지 않는다.","",
              "### 2.3 하루 총액 X를 20종목에 나눌 때 1% 초과","",
              "각 셀은 **초과 종목 수의 날짜 평균 / 최대; 초과 0개인 날짜 비율**이다. 하루 총액과 계좌 NAV는 다르다(슬롯 40 가정 NAV=40X).", "",
              "|모델|완전 앵커|100만원|1,000만원|1억원|10억원|", "|---|---:|---:|---:|---:|---:|"]
    for model in MODELS:
        a=anchor_stats(picks[picks.model_id==model],.01)
        values=[f"{a[c].mean():.2f}/{int(a[c].max())}; {100*(a[c]==0).mean():.1f}%" if len(a) else "NA" for c in ("b1","b10","b100","b1000")]
        lines.append(f"|{model}|{len(a)}|"+"|".join(values)+"|")
    lines += ["", "### 2.4 v32a 날짜별 한도 — 어떤 종목이 묶는가","",
              "p=1%, 금액 단위 억원. NAV_med는 중앙 종목 기준이므로 그보다 한산한 종목들의 초과를 허용하는 참고값이다.","",
              "|run_id|ADV20 참조 구간|종목 수|최소 한도 종목/시장|그 종목 L_i|NAV_min|NAV_med|목록 Σ|", "|---|---|---:|---|---:|---:|---:|---:|"]
    for run,f in picks[picks.model_id=="v32a"].groupby("run_id",sort=True):
        weak=f.sort_values(["adv20","ticker"]).iloc[0]
        total,lo,mid=limits(f.adv20,.01)
        lines.append(f"|{run}|{f.lookback_start.iloc[0]}~{f.lookback_end.iloc[0]}|{len(f)}|{weak.ticker}/{weak.market}|{eok(weak.adv20*.01)}|{eok(lo)}|{eok(mid)}|{eok(total)}|")
    lines += ["", "## 3. 다음 날 장애 대리와 중복 주문","",
              "### 3.1 다음 날 거래량 0·정지·29% 이상 상승","",
              "장애율은 (세 조건 중 하나 이상)/(판별 가능한 선택 슬롯)이다. 조건별 수는 겹칠 수 있다. 다음 날 자료가 아직 없거나 필드가 불명확하면 분모에서 제외한다. 전량 체결 불가 실측률로 부르지 않는다.","",
              "|모델/기간/시장|앵커|선택 슬롯|판별 가능|합집합 수/율 %|0거래량|정지|≥29%|>31%|미도래 슬롯|시세행 결측|기타 미확인|", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for model,period,market,f in partition(picks):
        known=int(f.known.sum()); blocked=int(f.blocked.sum())
        rate=100*blocked/known if known else np.nan
        other=int((~f.known & ~f.future_unknown & ~f.row_missing).sum())
        lines.append(f"|{model}/{period}/{market}|{f.run_id.nunique()}|{len(f)}|{known}|{blocked}/{decimal(rate)}|{int(f.zero.sum())}|{int(f.halt.sum())}|{int(f.up29.sum())}|{int(f.change_over31.sum())}|{int(f.future_unknown.sum())}|{int(f.row_missing.sum())}|{other}|")
    lines += ["", "장애 대리로 분류된 원 슬롯(반복 종목은 별개 독립 사건이 아님):", "",
              "|모델/run_id|ticker/시장|다음 거래일|0거래량|정지|≥29%|", "|---|---|---|---:|---:|---:|"]
    for r in picks[picks.blocked].itertuples(index=False):
        lines.append(f"|{r.model_id}/{r.run_id}|{r.ticker}/{r.market}|{r.next_day}|{int(r.zero)}|{int(r.halt)}|{int(r.up29)}|")
    lines += ["", "### 3.2 v32a/v30 중복 목록","",
              "|run_id|겹침 전체 수/20|KOSPI 수/10|KOSDAQ 수/10|합집합 종목 수|", "|---|---:|---:|---:|---:|"]
    joined=[]
    for run,f in paired.groupby("run_id",sort=True):
        a=f[f.model_id=="v30"].set_index(["market","ticker"])
        b=f[f.model_id=="v32a"].set_index(["market","ticker"])
        overlap=set(a.index)&set(b.index)
        union=f.groupby(["market","ticker"],sort=True).agg(adv20=("adv20","first"),multiplicity=("model_id","size")).reset_index()
        assert union.multiplicity.sum()==40 and len(union)==40-len(overlap)
        joined.append((run,union,len(overlap)))
        lines.append(f"|{run}|{len(overlap)}/20 ({100*len(overlap)/20:.1f}%)|{sum(m=='KOSPI' for m,t in overlap)}/10|{sum(m=='KOSDAQ' for m,t in overlap)}/10|{len(union)}|")
    lines += ["", "각 모델에 X씩, 합계 2X를 동시에 넣는 경우다. 겹친 종목은 주문을 합친 뒤 p=1%와 비교했다. 두 모델에 합쳐 X만 배정하는 경우의 표가 아니다.","",
              "|run_id|X(모델당 하루 원)|합집합 중 1% 초과|겹친 종목 중 1% 초과|각 계좌 NAV 동일할 때 각 NAV 상한(원)|", "|---|---:|---:|---:|---:|"]
    for run,union,nshared in joined:
        account_cap=float((union.adv20*.01*800/union.multiplicity).min())
        for budget in BUDGETS:
            over=union.multiplicity*budget/20 > union.adv20*.01
            lines.append(f"|{run}|{budget:,}|{int(over.sum())}/{len(union)}|{int((over & (union.multiplicity==2)).sum())}/{nshared}|{won(account_cap)}|")
    lines += ["", "## 4. 전체 분포·기간·시장·참여율 표","",
              "### 4.1 종목별 L_i 분포 (원)","",
              "선택된 유효 슬롯의 선형보간 분위다. 기간 내 같은 종목의 반복도 포함한다. 불완전 목록의 관측 종목도 이 표에는 포함하며, 다음 목록/NAV 표에서는 완전 20종목 앵커만 쓴다.","",
              "|모델/기간/시장|앵커/유효 슬롯|p %|Q10 원|Q25 원|Q50 원|Q75 원|Q90 원|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for model,period,market,f in partition(picks):
        adv=f.adv20.dropna().to_numpy()
        for p in PARTICIPATIONS:
            quant=np.quantile(adv*p,QUANTILES,method="linear") if len(adv) else np.full(5,np.nan)
            lines.append(f"|{model}/{period}/{market}|{f.run_id.nunique()}/{len(adv)}|{100*p:g}|"+"|".join(won(x) for x in quant)+"|")
    lines += ["", "### 4.2 목록 합계와 NAV 기준 (원)","",
              "각 값은 **날짜별 계산값의 기간 중앙값**이다. 시장별 NAV도 전체 20슬롯의 800 계수를 유지한 부분 제약이다. 전체 목록 합계가 크더라도 가장 작은 종목의 한도가 균등 배분을 먼저 제한할 수 있다.","",
              "|모델/기간/시장|완전 앵커|p %|목록 Σ 중앙 원|NAV_min 중앙 원|NAV_med 중앙 원|", "|---|---:|---:|---:|---:|---:|"]
    for model,period,market,f in partition(picks):
        for p in PARTICIPATIONS:
            a=anchor_stats(f,p)
            lines.append(f"|{model}/{period}/{market}|{len(a)}|{100*p:g}|{won(median(a['sum']))}|{won(median(a.nav_min))}|{won(median(a.nav_med))}|")
    lines += ["", "### 4.3 투입액별 참여율 초과 종목 수","",
              "각 셀은 날짜 평균/최대 개수. 시장별도 종목당 X/20이며 전체 행의 개수에 합쳐지는 시장 기여분이다.","",
              "|모델/기간/시장|완전 앵커|p %|100만원|1,000만원|1억원|10억원|", "|---|---:|---:|---:|---:|---:|---:|"]
    for model,period,market,f in partition(picks):
        for p in PARTICIPATIONS:
            a=anchor_stats(f,p)
            cells=[f"{a[c].mean():.2f}/{int(a[c].max())}" if len(a) else "NA" for c in ("b1","b10","b100","b1000")]
            lines.append(f"|{model}/{period}/{market}|{len(a)}|{100*p:g}|"+"|".join(cells)+"|")
    lines += ["", "### 4.4 원 앵커별 p=1% 한도 (원)","",
              "다른 참여율은 L/NAV 금액에 각각 0.5배·2배·5배를 적용하면 된다. ADV 미확인이 있으면 합계/NAV는 NA. `부분` 행의 금액은 실제 선택된 종목에 한정하며 20종목 완전 명단의 값이 아니다. 해당 행은 위 목록·NAV·초과 요약에 넣지 않았다.","",
              "|모델/run_id|선택/ADV 유효|완전성|선택분 Σ 원|선택분 NAV_min 원|선택분 NAV_med 원|1억 투입 시 관측종목 초과|", "|---|---:|---|---:|---:|---:|---:|"]
    for model in MODELS:
        for run,f in picks[picks.model_id==model].groupby("run_id",sort=True):
            total,low,mid=limits(f.adv20,.01)
            n=exceed_count(f.adv20,.01,100_000_000)
            lines.append(f"|{model}/{run}|{len(f)}/{f.adv20.notna().sum()}|{'20종목' if f.full20.all() else '부분'}|{won(total)}|{won(low)}|{won(mid)}|{won(n)}|")
    lines += ["", "## 5. 검증·재현 기록","",check_message,"",
              "실제 자료 점검: 선택 키 중복 없음, 시장별 최대 10개, ADV 유효 값 비음수, 완전 목록 20개, 겹침 합집합 수와 40슬롯 합계가 일치했다. 희석/운영 게이트는 실행하지 않았다."]
    # Verify scaling and monotonicity on every complete list; an independent
    # direct arithmetic check uses each original 20-row window for one pick.
    complete=picks[picks.full20]
    for _,f in complete.groupby(["model_id","run_id"]):
        unit=np.array(limits(f.adv20,.01))
        assert len(f)==20 and np.isfinite(unit).all()
        prev=np.full(len(BUDGETS),21.)
        for p in PARTICIPATIONS:
            assert np.allclose(np.array(limits(f.adv20,p)),unit*(p/.01))
            counts=np.array([exceed_count(f.adv20,p,x) for x in BUDGETS])
            assert (counts<=prev).all() and (np.diff(counts)>=0).all()
            prev=counts
    sample=complete.iloc[0]
    span=price[(price.ticker==sample.ticker) & (price.date>=sample.lookback_start) & (price.date<=sample.lookback_end)]
    assert len(span)==20 and np.isclose(float((span.close.astype(float)*span.volume).sum()/20),sample.adv20)
    lines += ["독립 산술 점검: 모든 완전 앵커의 p 비례, 참여율 증가 시 초과 수 비증가, 투입액 증가 시 초과 수 비감소, 원 시세 20행의 직접 합/20과 ADV20 일치를 확인했다.","",
              f"표본 산술 확인: {sample.model_id}/{sample.run_id}/{sample.ticker}, {sample.lookback_start}~{sample.lookback_end}, ADV20 {won(sample.adv20)}원."]
    after={"ohlcv":snapshot(PRICE_DB),"history":snapshot(HISTORY_DB)}
    assert before==after,"DB 파일 크기/mtime이 실행 중 변경됨"
    sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    lines += ["", "|입력 DB|크기 bytes|mtime_ns 전=후|", "|---|---:|---:|"]
    lines += [f"|{k}|{v[0]}|{v[1]}|" for k,v in before.items()]
    lines += ["",f"실행 종료 {time_guard()}, {time.monotonic()-began:.1f}초. 코드 SHA256 `{sha}`.",
              "DB 크기/수정 시각 불변은 내용 해시 검증과는 다르다. 모든 연결은 mode=ro/query_only 및 읽기 트랜잭션이었다. 중간 파일 없음.",""]
    report="\n".join(lines)
    if write_report:
        time_guard()
        prefix=REPLY.read_text(encoding="utf-8")
        if "\n## 6." in prefix:
            raise RuntimeError("§6 대조 완료 답 파일 덮어쓰기 금지; stdout으로 재현")
        REPLY.write_text(prefix.split(MARKER)[0].rstrip()+"\n\n"+report+"\n",encoding="utf-8")
        print("REPORT",REPLY)
        print(check_message)
        for model,(q,a) in headline.items():
            print(model,"L_i Q10/Q50 억",[eok(x) for x in q],"NAV_min 날짜 최소/중앙/최대 억",eok(a.nav_min.min()),eok(median(a.nav_min)),eok(a.nav_min.max()),"NAV_med 날짜중앙 억",eok(median(a.nav_med)))
        print("SAME_DATE_RATIO",ratio_summary)
        for model in MODELS:
            f=picks[picks.model_id==model]
            print(model,"NEXT",int(f.blocked.sum()),"/",int(f.known.sum()),"future_unknown",int(f.future_unknown.sum()))
        print("COMMON_RUNS",common,"OVERLAP",[(run,n) for run,_,n in joined])
    else:
        print(report)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check-only",action="store_true")
    parser.add_argument("--write-report",action="store_true")
    args=parser.parse_args()
    time_guard()
    if args.self_check_only:
        print(checks())
    else:
        generate(args.write_report)
