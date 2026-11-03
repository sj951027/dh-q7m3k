"""J05 offline wrapper. Imports the unmodified operating engine; never calls run().

python -X utf8 -B research/handoff/code_20261102_j05_replace_vs_cash.py
Output: requested REPLY plus files only inside out_20261102_j05.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import sqlite3
import sys
from unittest.mock import patch
from urllib.parse import unquote

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'dh-q7m3k-data'
OUT=ROOT/'research/handoff/out_20261102_j05'
REPLY=ROOT/'research/handoff/REPLY_20261102_j05_replace_vs_cash.md'
SOURCES={'v30':('v3_scores','final_score_v3'),'lv_b':('lowvol_scores','lowvol_score'),'v32a':('v3_scores','final_score_v3')}
DBS=[ROOT/'history.db',DATA/'ohlcv.db']
CONNECT=sqlite3.connect
CONNECTIONS=[]


def guard():
    n=datetime.now(ZoneInfo('Asia/Seoul'))
    if n.weekday()<5 and '20:10'<=n.strftime('%H:%M')<'22:30':raise RuntimeError('Batch window')
    return n.isoformat(timespec='seconds')


def readonly_connect(database,*args,**kwargs):
    guard();uri=str(database)
    if not uri.startswith('file:') or '?mode=ro' not in uri or not kwargs.get('uri'):
        raise RuntimeError('Only explicit read-only database URI allowed')
    name=unquote(uri[5:].split('?')[0])
    if name.startswith('///'):name=name[3:]
    target=Path(name).resolve()
    if target not in [x.resolve() for x in DBS]:raise RuntimeError('DB outside request')
    c=CONNECT(database,*args,**kwargs);c.execute('PRAGMA query_only=ON')
    CONNECTIONS.append(str(target));return c


def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Network disabled')
    if event=='open':
        path,mode,flags=args
        writing=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
        if writing and isinstance(path,(str,bytes,os.PathLike)):
            if os.path.normcase(os.fsdecode(path))==os.path.normcase(os.devnull):return
            p=Path(os.fsdecode(path)).resolve()
            if not p.is_relative_to(OUT.resolve()) and p!=REPLY.resolve():raise RuntimeError('Write outside requested outputs')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def state(path):
    s=path.stat();return [s.st_size,s.st_mtime_ns]
def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,(np.integer,)):return int(x)
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    return x
def dump(path,value):guard();path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def ranked_candidates(pa,pe,mid,dates,didx,excluded):
    """Existing score rank helper; the imported model_picks is checked against top10."""
    table,col=SOURCES[mid]
    c=sqlite3.connect((ROOT/'history.db').as_uri()+'?mode=ro',uri=True)
    try:S=pd.read_sql_query(f'SELECT run_id,market,ticker,{col} AS score FROM {table} WHERE model_id=?',c,params=(mid,))
    finally:c.close()
    S['run_id']=S.run_id.astype(str);S['ticker']=S.ticker.astype(str).str.zfill(6);S['market']=S.market.str.lower()
    keep=pa.lb.dedupe_by_anchor(S,didx,excluded,reg=pa.REG_V30 if mid=='v30' else None)
    result={};run_map={}
    for rid in sorted(keep):
        t=pa.lb.anchor(rid,didx);d=dates[t]
        if d<pa.START_DEFAULT:continue
        f=S[S.run_id==rid].dropna(subset=['score']);excluded_tickers=pa._dil_flags(rid)
        result[d]={};run_map[d]=rid
        for market,g in f.groupby('market'):
            # Same helper as production, with only its documented top parameter changed.
            result[d][market]=pe.picks_from_scores(g,top=15,exclude=excluded_tickers).get(rid,[])
    return result,run_map


def reasons(raw,date,ticker,close,tradable,limit):
    labels=[]
    px=close.at[date,ticker] if ticker in close.columns else np.nan
    if not np.isfinite(px) or px<=0:labels.append('시세없음')
    key=(date,ticker)
    if key in raw.index:
        r=raw.loc[key]
        if pd.notna(r.is_suspended) and r.is_suspended>0:labels.append('정지플래그')
        if pd.notna(r.volume) and r.volume==0:labels.append('거래량0')
        if pd.notna(r.change_pct) and r.change_pct>=limit:labels.append('상한가')
    if not labels:labels.append('tradable=False')
    return '+'.join(labels)


def can_enter(close,tradable,date,ticker):
    if ticker not in close.columns:return False
    px=close.at[date,ticker]
    if not np.isfinite(px) or px<=0:return False
    flag=tradable.at[date,ticker] if ticker in tradable.columns else True
    return bool(flag) if pd.notna(flag) else True


def replacements(base,ranks,run_map,dates,close,tradable,raw,pe,pa,mid):
    didx={d:i for i,d in enumerate(dates)}
    changed={d:list(v) for d,v in base.items()};events=[];attempts=0;zero_unblocked=0
    for anchor,original in base.items():
        i=didx[anchor]+pe.ENTRY_LAG
        if i>=len(dates):continue
        date=dates[i];attempts+=len(original)
        flat=[tk for market in sorted(ranks[anchor]) for tk in ranks[anchor][market][:pa.TOP]]
        assert flat==original,'Candidate top10 differs from imported production picks'
        assert len(set(original))==len(original)
        used=set(original)
        for market,ranked in ranks[anchor].items():
            top=ranked[:pa.TOP]
            for rank,ticker in enumerate(top,1):
                if can_enter(close,tradable,date,ticker):
                    if (date,ticker) in raw.index and raw.loc[(date,ticker),'volume']==0:zero_unblocked+=1
                    continue
                candidates=[];chosen=None;chosen_rank=None
                for k,candidate in enumerate(ranked[pa.TOP:15],pa.TOP+1):
                    good=candidate not in used and can_enter(close,tradable,date,candidate)
                    candidates.append({'rank':k,'ticker':candidate,'available':good})
                    if good:chosen=candidate;chosen_rank=k;break
                if chosen:
                    pos=changed[anchor].index(ticker);changed[anchor][pos]=chosen;used.add(chosen)
                # If no substitute, retain the original blocked entry to preserve its cash weight.
                events.append({'model':mid,'run_id':run_map[anchor],'anchor_date':anchor,'entry_date':date,
                    'market':market,'original_rank':rank,'original_ticker':ticker,
                    'reason':reasons(raw,date,ticker,close,tradable,pa.LIMIT_UP),'replacement':chosen,
                    'replacement_rank':chosen_rank,'candidates_checked':json.dumps(candidates,ensure_ascii=False),
                    'entry_i':i,'planned_exit_i':i+pe.HOLD})
        assert len(changed[anchor])==len(original) and len(set(changed[anchor]))==len(original)
    return changed,events,attempts,zero_unblocked


def return40(pe,dates,close,i,ticker):
    if not ticker or ticker not in close.columns or i+pe.HOLD>=len(dates):return None,None,None
    p=close.at[dates[i],ticker]
    if not np.isfinite(p) or p<=0:return None,None,None
    arr=close[[ticker]].to_numpy(float)
    x=pe.last_px(arr,0,i+pe.HOLD)
    if not np.isfinite(x):return None,None,None
    gross=(x/p-1)*100;net=(x/p*(1-pe.COST_MAIN/2)**2-1)*100
    return gross,net,dates[i+pe.HOLD]


def report(summary,events,run):
    lines=['# REPLY — J05 못 사는 종목의 다음 순위 대체 vs 현금','',
      f"실측 되감기 {run['start']}~{run['end']} ({run['days']}거래일). 기존 paper_engine/paper_account를 import했고 simulate·load_prices·v30_picks·model_picks·_dil_flags를 그대로 사용했다. SLOTS={run['constants']['slots']}, HOLD={run['constants']['hold']}, ENTRY_LAG={run['constants']['entry_lag']}, COST_MAIN={run['constants']['cost']}, LIMIT_UP={run['constants']['limit_up']}, TOP={run['constants']['top']}, settle_days=0. PAPER_USE_EXTRA=1: daily_ohlcv_extra와 daily_ohlcv를 합치며 동일 키는 본표 우선.",
      '', '## 1. 방법·경계','',
      '- 기준 목록은 운영 함수가 반환한 시장별 상위 10과 동일. 후보 순위는 같은 동결점수·앵커/게이트·희석 제외와 기존 picks_from_scores(top=15)로 만들고 앞 10개가 기준과 완전히 같은지 전수 확인했다.',
      '- 진입일 t+1의 기존 tradable과 양수 종가 존재만으로 대체 여부를 정했다. 같은 시장 11~15위에서 사용하지 않은 첫 매수 가능 종목으로 교체. 후보가 없으면 원래 막힌 항목을 그대로 남겨 그 몫을 현금으로 보존했다. 목록 길이를 줄여 재분배하지 않았다.',
      '- 거래량 0은 기존 is_suspended 플래그로 엔진에 반영된다. 별도의 새 거래량 필터는 추가하지 않았다. 장 마감 때 확정되는 거래량과 상한가 여부를 종가 주문에 쓸 수 있다는 실무 시각 가정은 남는다.',
      '- B 지연 진입은 생략(엔진 밖). 엔진의 entry_lag는 전체 입력에 하나이고, 원래 슬롯 예산을 보존한 종목별 대기 주문을 지원하지 않는다. 추천일을 옮겨 넣으면 슬롯 예산·기준 NAV도 달라져 같은 변수 비교가 아니다.',
      '- slots=40은 보유 기간을 나누는 자금 묶음 수다. 아래 발생률의 분모는 진입일이 존재하는 추천 종목×날짜 슬롯 수이며, 계좌별 40이나 실제 체결 수를 분모로 쓰지 않았다.',
      '', '## 2. 기준 vs 대체 A','',
      '|모델|진입일 있는 종목 슬롯|막힌 슬롯|실제 대체|대체 날|대체 비율 %|기준 수익 %|A 수익 %|차 %p|기준 최대낙폭 %|A 최대낙폭 %|차 %p|기준 평균현금 %|A 평균현금 %|차 %p|',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mid,s in summary.items():
        b=s['baseline'];a=s['replace_A'];z=s['delta']
        lines.append('|'+ '|'.join([mid,str(s['attempted_stock_slots']),str(s['blocked_slots']),str(s['executed_replacements']),str(s['replacement_days']),f"{s['replacement_rate_pct']:.3f}"]+[f"{x:.6f}" for x in [b['total_ret'],a['total_ret'],z['total_ret'],b['mdd'],a['mdd'],z['mdd'],b['cash_share'],a['cash_share'],z['cash_share']]])+'|')
    lines += ['', '표의 최대낙폭은 기존 summarize의 음수 값이다. 평균현금은 일별 cash/nav의 산술평균. 전체 되감기 경로의 실측치이며 모집단 평균을 추정한 표본이 아니므로 이 계좌 총수익에 임의의 신뢰구간을 붙이지 않았다.',
      '', '## 3. 발생 목록·40일 결과','',
      '|모델|추천일|진입일|시장|원 종목|이유|대체(순위)|대체 40일 총수익 %|원 종목 가상 40일 %|상태|','|---|---|---|---|---|---|---|---:|---:|---|']
    def fmt(x):return '미관측' if x is None or pd.isna(x) else f'{x:.3f}'
    for e in events:
        lines.append(f"|{e['model']}|{e['anchor_date']}|{e['entry_date']}|{e['market']}|{e['original_ticker']}|{e['reason']}|{e['replacement'] or '현금'} ({e['replacement_rank'] or '—'})|{fmt(e['replacement_gross40_pct'])}|{fmt(e['original_hypothetical_gross40_pct'])}|{e['return40_status']}|")
    if not events:lines.append('|발생 0|—|—|—|—|—|—|—|—|—|')
    lines += ['', '현금 비교 수익은 0%. 40거래일이 아직 지나지 않은 건은 마지막 날 평가수익을 40일 수익으로 바꾸지 않았다. 원 종목의 가상 수익은 매수가 불가능했다는 사실을 무시한 t+1 종가 기준 참고값이며 실행 가능한 대안이 아니다. 시세가 없으면 그 가상 값도 미관측이다. 40일 만기에 시세가 없으면 기존 엔진의 마지막 유효 종가 규칙을 따른다. events.csv에는 비용 포함 40일 값도 별도 보존했다.',
      '', '## 4. 결론·검증·재현','']
    for mid,s in summary.items():
        lines.append(f"- **{mid}: {s['decision']}**. 대체 {s['executed_replacements']}/{s['attempted_stock_slots']}슬롯, 전체 수익 차이 {s['delta']['total_ret']:+.6f}%p. 앵커 {s['anchors']}개, 첫 앵커 {s['first_anchor']}, 진입일 없는 마지막 앵커 {s['anchors_without_entry']}개.")
    lines += ['', 'v32a는 짧은 등록 구간의 참고다. 발생 0은 장기 영향 0의 증거가 아니다. 13장 중 세 모델만 계산했으며 규칙 채택·다른 계좌 변경은 하지 않았다.',
      '기존 엔진 파일/배선 파일/소비 장부·JSON의 해시 또는 크기·수정 시각 전후 일치. 모든 DB 연결은 허용된 두 파일의 mode=ro + query_only로 강제했고 네트워크 호출을 막았다. paper_account.run은 호출하지 않았다. 출력은 명시된 코드·REPLY와 out_20261102_j05 아래에 한정했다.',
      f"원래 tradable이 허용한 거래량 0 기준 슬롯은 {sum(s['volume_zero_but_allowed'] for s in summary.values())}개였다. 개별 후보의 가용성·순위·동일 시장·중복 없음·기준/대체 목록 길이 보존·엔진 체결 내역을 검증했다.",
      '', '`python -X utf8 -B research/handoff/code_20261102_j05_replace_vs_cash.py`',
      f"코드 SHA256 `{run['code_sha256']}`. 입력·엔진 해시, 상수, 요약은 summary.json, 목록은 picks.csv, 발생은 events.csv, 일별 경로·체결은 모델별 nav/ledger CSV에 있다. §5 대조 전 blind_freeze.json을 저장했다.",
      '', '## 5. 결과 고정 후 J10·J06 대조','', '아직 지정 비교 문서를 열지 않은 독립 결과다. 고정 후 이 절만 추가한다.','']
    return '\n'.join(lines)


def main():
    started=guard();OUT.mkdir(exist_ok=True);sys.dont_write_bytecode=True
    sys.addaudithook(audit);sys.path.insert(0,str(ROOT))
    # These imports define functions/constants only; no run(), collectors, or score recalculation.
    import paper_account as pa
    import paper_engine as pe
    if os.environ.get('PAPER_USE_EXTRA','1')=='0':raise RuntimeError('PAPER_USE_EXTRA must be enabled')
    assert Path(pa.lb.OHLCV_DB).resolve()==(DATA/'ohlcv.db').resolve()
    files=[ROOT/'paper_engine.py',ROOT/'paper_account.py',ROOT/'docs/paper_account.json']
    hashes={str(p):sha(p) for p in files}
    states={str(p):state(p) for p in DBS+[DATA/'paper_account.db']}
    run={'started_at':started,'code_sha256':sha(Path(__file__)),'protected_hashes':hashes,'db_states':states,
         'constants':{'slots':pe.SLOTS,'hold':pe.HOLD,'entry_lag':pe.ENTRY_LAG,'cost':pe.COST_MAIN,'limit_up':pa.LIMIT_UP,'top':pa.TOP,'settle_days':0}}
    summaries={};all_events=[];pick_rows=[]
    with patch.object(sqlite3,'connect',readonly_connect):
        close,trd,shares,mkt=pa.load_prices();all_dates=list(close.index);all_idx={d:i for i,d in enumerate(all_dates)}
        excluded=pa.load_gates(all_dates)
        dates=[d for d in all_dates if d>=pa.START_DEFAULT];sub=close.loc[dates];tradable=trd.reindex(index=dates)
        run.update(start=dates[0],end=dates[-1],days=len(dates),price_tickers=len(sub.columns),gate_excluded_runs=sorted(excluded))
        print('price loaded',sub.shape,dates[0],dates[-1],flush=True)
        c=sqlite3.connect((DATA/'ohlcv.db').as_uri()+'?mode=ro',uri=True)
        try:
            raw=[pd.read_sql_query(f'SELECT ticker,date,volume,is_suspended,change_pct FROM {table} WHERE date>=?',c,params=(pa.START_DEFAULT,)) for table in ['daily_ohlcv_extra','daily_ohlcv']]
        finally:c.close()
        raw=pd.concat(raw,ignore_index=True);raw['ticker']=raw.ticker.astype(str).str.zfill(6)
        raw=raw.drop_duplicates(['date','ticker'],keep='last').set_index(['date','ticker']).sort_index()
        for mid,(table,col) in SOURCES.items():
            pk=pa.v30_picks(all_dates,all_idx,excluded) if mid=='v30' else pa.model_picks(mid,table,col,all_dates,all_idx,excluded,reg=None)
            base={d:v for d,v in pk.items() if d>=pa.START_DEFAULT}
            ranked,run_map=ranked_candidates(pa,pe,mid,all_dates,all_idx,excluded)
            changed,events,attempts,zero=replacements(base,ranked,run_map,dates,sub,tradable,raw,pe,pa,mid)
            nav0,ledger0=pe.simulate(dates,sub,base,tradable=tradable,settle_days=0)
            nav1,ledger1=pe.simulate(dates,sub,changed,tradable=tradable,settle_days=0)
            s0=pe.summarize(nav0);s1=pe.summarize(nav1)
            ledger_map={(p['run'],p['ticker']):p for p in ledger1}
            base_entries={(p['run'],p['ticker']) for p in ledger0}
            count=0
            for e in events:
                assert (e['anchor_date'],e['original_ticker']) not in base_entries
                gross,net,exit_date=return40(pe,dates,sub,e['entry_i'],e['replacement'])
                og,on,_=return40(pe,dates,sub,e['entry_i'],e['original_ticker'])
                e.update(replacement_gross40_pct=gross,replacement_net40_pct=net,original_hypothetical_gross40_pct=og,
                         original_hypothetical_net40_pct=on,exit_date=exit_date,
                         return40_status='완결' if e['planned_exit_i']<len(dates) else '40일 미완결',cash_return_pct=0.)
                p=ledger_map.get((e['anchor_date'],e['replacement'])) if e['replacement'] else None
                e['executed']=p is not None;e['replacement_invested']=p['invested'] if p else 0.
                if e['replacement']:
                    assert p is not None,'Planned replacement not executed (cash budget?)';count+=1
                    if net is not None:assert abs(p['ret']*100-net)<1e-9
            if count==0:pd.testing.assert_frame_equal(nav0,nav1)
            delta={key:s1[key]-s0[key] for key in ['total_ret','mdd','cash_share']}
            rate=100*count/attempts if attempts else 0.
            decision='검토' if abs(delta['total_ret'])>=.3 else '후순위 닫음(규칙 유지 = 현금)' if rate<=1 else '사전 조건표 미분류(차이<0.3%p·발생>1%)'
            if not count:decision+=' · 발생 0'
            summaries[mid]={'baseline':s0,'replace_A':s1,'delta':delta,'attempted_stock_slots':attempts,'blocked_slots':len(events),
                'executed_replacements':count,'replacement_days':len({e['entry_date'] for e in events if e['executed']}),
                'replacement_rate_pct':rate,'blocked_rate_pct':100*len(events)/attempts if attempts else 0.,
                'anchors':len(base),'first_anchor':min(base) if base else None,
                'anchors_without_entry':sum(dates.index(d)+pe.ENTRY_LAG>=len(dates) for d in base),
                'volume_zero_but_allowed':zero,'decision':decision}
            for d,lst in base.items():
                for k,(a,b) in enumerate(zip(lst,changed[d]),1):pick_rows.append({'model':mid,'anchor':d,'position':k,'baseline':a,'replace_A':b})
            for label,nav,ledger in [('cash',nav0,ledger0),('replace_A',nav1,ledger1)]:
                nav.to_csv(OUT/f'{mid}_{label}_nav.csv',index=False,encoding='utf-8-sig')
                pd.DataFrame(ledger).to_csv(OUT/f'{mid}_{label}_ledger.csv',index=False,encoding='utf-8-sig')
            all_events+=events;print(mid,summaries[mid],flush=True)
    assert hashes=={str(p):sha(p) for p in files}
    assert states=={str(p):state(p) for p in DBS+[DATA/'paper_account.db']}
    run.update(finished_at=guard(),readonly_connections=len(CONNECTIONS),connection_paths=sorted(set(CONNECTIONS)))
    dump(OUT/'summary.json',{'run':run,'models':summaries})
    pd.DataFrame(pick_rows).to_csv(OUT/'picks.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(all_events).to_csv(OUT/'events.csv',index=False,encoding='utf-8-sig')
    REPLY.write_text(report(summaries,all_events,run),encoding='utf-8')
    dump(OUT/'blind_freeze.json',{'frozen_at':guard(),'code_sha256':run['code_sha256'],
        'files':{p.name:sha(p) for p in sorted(OUT.glob('*.csv'))+[OUT/'summary.json']},'blind_reply_sha256':sha(REPLY)})
    print('FROZEN',OUT/'blind_freeze.json',flush=True)


if __name__=='__main__':main()
