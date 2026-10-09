"""Independent review; fake responses/memory databases and read-only snapshots only.
Run: python -B research/handoff/code_20261010_recheck.py
Never invokes collector main(), batch, DART or KIS. Only REPLY is retained.
2026-10-09 holiday blackout exception explicitly authorized by the user.
"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
from datetime import datetime, timedelta, timezone
import sqlite3, shutil, tempfile, hashlib, importlib.util, inspect, math, json
from collections import Counter
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261010_recheck.md')
sys.path.insert(0, str(ROOT))
import earnings_incr as X
import pandas as pd


def guard():
    t = datetime.now(timezone(timedelta(hours=9)))
    if t.strftime('%Y%m%d') != '20261009' and t.weekday() < 5 and '20:10' <= t.strftime('%H:%M') < '22:30':
        raise SystemExit('KST batch window; existing REPLY retained')
    return t.isoformat(timespec='seconds')


def ro(p):
    return sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True)


def md(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---']*len(headers)) + '|'] +
                     ['| ' + ' | '.join(str(v).replace('|', '/') for v in row) + ' |' for row in rows])


def op(th, add=None, prev=None, prevadd=None, annualprev=None, receipt=None):
    d = dict(account_id='dart_OperatingIncomeLoss', sj_div='IS', account_nm='영업이익')
    for k, v in [('thstrm_amount', th), ('thstrm_add_amount', add), ('frmtrm_q_amount', prev),
                 ('frmtrm_add_amount', prevadd), ('frmtrm_amount', annualprev)]:
        d[k] = '' if v is None else str(v)
    if receipt: d['rcept_no'] = receipt
    return [d]


def filing(t='111111', r='Q3', receipt='20261114000001', date='20261114', amend=False):
    ym = {'Q1': '2026.03', 'H1': '2026.06', 'Q3': '2026.09', 'Y': '2025.12'}[r]
    name = {'Q1': '분기', 'H1': '반기', 'Q3': '분기', 'Y': '사업'}[r] + '보고서'
    return X.parse_filing(dict(corp_cls='Y', stock_code=t, corp_code=t,
                              report_nm=('정정' if amend else '') + name + ' (' + ym + ')',
                              rcept_no=receipt, rcept_dt=date))


class Lab:
    def __init__(self, priced=True):
        self.c = X.open_db(':memory:')
        self.o = sqlite3.connect(':memory:')
        self.o.executescript('CREATE TABLE daily_ohlcv(ticker,date,close,shares); CREATE TABLE daily_ohlcv_extra(ticker,date,close,shares);')
        self.fin, self.calls = {}, []
        if priced: self.price()

    def price(self, t='111111', date='20261113', close=100, shares=1000):
        self.o.execute('INSERT INTO daily_ohlcv VALUES(?,?,?,?)', (t,date,close,shares)); self.o.commit()

    def put(self, rows, year=2026, r='Q3', fs='CFS', t='111111'):
        self.fin[(t,str(year),X.REPRT_CODE[r],fs)] = rows

    def fake(self, url, params, key):
        assert url == X.FIN_URL
        self.calls.append(dict(params))
        rows = self.fin.get(tuple(params[k] for k in ('corp_code','bsns_year','reprt_code','fs_div')))
        return dict(status='000',list=rows) if rows else dict(status='013',list=[])

    def run(self, fs=(), now=datetime(2026,11,14), **kw):
        guard()
        return X.process(self.c,self.o,list(fs),'FAKE',fetch=self.fake,now=now,**kw)

    def q(self):
        return self.c.execute('SELECT ticker,year,reprt,q_op,q_op_prev,rcept_dt FROM earnings_q ORDER BY ticker,year,reprt').fetchall()

    def pending(self):
        return self.c.execute('SELECT rcept_no,reason,tries FROM earnings_pending ORDER BY rcept_no').fetchall()

    def state(self):
        return self.c.execute('SELECT rcept_no,state FROM earnings_raw ORDER BY year,reprt').fetchall()


def earnings_cases():
    results = []
    def save(label, evidence): results.append([label, evidence])
    f = filing()
    a=Lab(False); a.put(op(120,300,100,250)); c1=a.run([f]); a.price(); c2=a.run()
    assert c1['no_price']==c2['new']==1 and not a.pending() and len(a.calls)==1
    save('이전① 시세 없음 뒤 보충', f"회복: q={a.q()}; 첫 no_price=1, 다음 new=1, 전체 호출 n=1, 큐 n=0")
    a=Lab(False); a.price(date='20260309'); a.put(op(5000,annualprev=4000),year=2025,r='Y')
    fy=filing(r='Y',receipt='20260310000001',date='20260310')
    c1=a.run([fy],now=datetime(2026,3,10)); a.put(op(1500,3500,1100,3000),year=2025,r='Q3')
    c2=a.run(now=datetime(2026,3,11)); assert c1['no_values']==c2['new']==1 and a.q()[0][3:5]==(1500,1000)
    save('이전② 연간 보고서의 Q3 결손', f"회복: Q4=(1500,1000), 호출 n={len(a.calls)}, 큐 n={len(a.pending())}")
    a=Lab(); a.put(op(120,300,100)); c=a.run([f,f]); assert len(a.q())==1 and len(a.calls)==1
    save('같은 보고서 중복', f"입력 n=2, q n={len(a.q())}, 호출 n={len(a.calls)}, done n={c['done']}")
    am=filing(receipt='20261116000009',date='20261116',amend=True)
    for reverse in (False,True):
        a=Lab(); a.put(op(150,300,100))
        p, fresh=(f,am) if reverse else (am,f)
        X.pend(a.c,p,'budget','20261114_0000',count_try=False)
        c=a.run([fresh],now=datetime(2026,11,16))
        save('원본 대기+새 정정본' if reverse else '정정본 대기+새 원본',
             f"정정 건너뜀 n={c['amend_no_orig']}, new n={c['new']}, updated n={c['updated']}, 호출 n={c['calls']}, 큐 n={len(a.pending())}; 전자는 정정본을 먼저 버림")
    a=Lab(); a.put(op(60000,100000,0)); c1=a.run([f]); a.put(op(120,300,100)); c2=a.run([am],now=datetime(2026,11,16))
    assert c1['extreme']==c2['amend_no_orig']==1 and not a.q()
    save('극단값 원본 뒤 정상 정정본', f"실패: extreme n=1 → amend_no_orig n=1, q n=0, 큐 n=0, raw={a.state()}")
    a=Lab(); a.put(op(120,300,None)); c1=a.run([f]); a.put(op(120,300,100)); c2=a.run(now=datetime(2026,11,15))
    assert c1['no_values']==c2['no_values']==1 and not a.q()
    save('받은 원자료의 빈 필드가 나중에 채워짐', f"회복 안 됨: 자기 보고서는 재조회 안 함, no_values n=2, q n=0, 큐={a.pending()}, 재호출은 의존 보고서만 n={c2['calls']}")
    a=Lab(); daily=[]
    for i in range(21):
        c=a.run([f] if i==0 else [],now=datetime(2026,11,14)+timedelta(days=i)); daily.append(c['calls'])
    assert daily==[2]*20+[0] and not a.pending()
    save('재무 조회 지속 실패', f"하루 CFS/OFS n=2, n=20회 합계 n={sum(daily)}, n=21번째 실행에서 삭제; 지연 재시도 없음")
    a=Lab(); X.pend(a.c,f,'budget','20261114_0000',count_try=False)
    c=a.run(now=datetime(2026,12,30),max_calls=0); assert c['pending_dropped']==1
    save('예산으로만 미룬 큐의 만료', '시도 n=0이어도 n=46일 뒤 삭제 n=1; last_end가 앞으로 갔으면 원 보고서를 다시 못 봄')
    a=Lab(); a.put(op(100,300),fs='OFS'); a.put(op(20,200,prevadd=150),r='H1',fs='OFS'); a.put(op(80,200),year=2025,fs='OFS')
    c=a.run([f],max_calls=1); assert c['calls']==6
    save('보고서 안의 호출 상한', f"max_calls=1인데 실제 논리 호출 n={c['calls']}; 보고서 중간에는 상한 검사 없음")
    a=Lab(); a.put(op(100,300,80)); fs=[f,filing(t='222222',receipt='20261114000002')]
    a.price('222222'); a.put(op(100,300,80),t='222222')
    c1=a.run(fs,max_calls=1); X.meta_set(a.c,'last_end','20261114'); a.c.commit(); c2=a.run(now=datetime(2026,11,18))
    assert len(a.q())==2 and not a.pending()
    save('last_end 전진 뒤 예산 대기', f"n=2건 중 첫 new n={c1['new']}, deferred n={c1['deferred']}, 조회 목록 없는 다음 new n={c2['new']}; 정상 회복")
    a=Lab(); a.put(op(100,300,80)); c1=a.run([f],max_seconds=0); c2=a.run()
    assert c1['deferred']==c2['new']==1
    save('시간 상한 대기', 'max_seconds=0: 대기 n=1 → 다음 실행 저장 n=1')
    a=Lab(); a.put(op(100,300,80)); clock=[0.0]
    def slow(url,params,key): clock[0]+=100; return a.fake(url,params,key)
    with patch.object(X.time,'time',side_effect=lambda:clock[0]):
        c=X.process(a.c,a.o,[f],'FAKE',fetch=slow,now=datetime(2026,11,14),max_seconds=1)
    assert c['new']==1 and clock[0]==100
    save('진행 중 조회의 시간 상한', '가짜 시계: max_seconds=1이지만 단일 조회 n=100초까지 완료; 강제 중단 상한 아님')
    n=[0]
    def get(*args,**kwargs):
        n[0]+=1; return SimpleNamespace(json=lambda:dict(status='900') if n[0]<3 else dict(status='000',list=op(100,300,80)))
    with patch.dict(sys.modules,{'requests':SimpleNamespace(get=get)}), patch.object(X._drate,'wait',return_value=0), patch.object(X.time,'sleep',return_value=None):
        raw,calls,status=X.fetch_report('FAKE','111111',2026,'Q3',f['rcept_no'],X.fetch_json)
    assert calls==1 and n[0]==3
    save('HTTP 재시도 계수', f"논리 호출 n={calls}, 가짜 HTTP 요청 n={n[0]}; 실제 HTTP 4,000회 상한은 아님")
    eager_globals=dict(X.__dict__)
    exec(compile(inspect.getsource(X.process).replace('if q_this is None or cumulative:', 'if True:'),'<memory-eager-process>','exec'),eager_globals)
    for label, raw, deps, expected in [
        ('3개월 칸에 누적',op(300,300,90),[('H1',2026,op(50,200,40,150)),('Q3',2025,op(90,250))],(100,90)),
        ('전년 3개월 0',op(100,300,0),[('H1',2026,op(50,200,40,150)),('Q3',2025,op(90,250))],(100,0))]:
        obs=[]
        for eager in (False,True):
            a=Lab(); a.put(raw)
            for r,y,dep in deps: a.put(dep,year=y,r=r)
            c=eager_globals['process'](a.c,a.o,[f],'FAKE',fetch=a.fake,now=datetime(2026,11,14)) if eager else a.run([f])
            obs.append((a.q()[0][3:5],c['calls']))
        assert obs[0][0]==obs[1][0]==expected
        save('의존 보고서: '+label,f"새 방식/항상 수신 결과 동일 {expected}; 논리 호출 n={obs[0][1]}/{obs[1][1]}")
    obs=[]
    for eager in (False,True):
        a=Lab(); a.put(op(100,300,90)); a.put(op(200,200,80,150),r='H1'); a.put(op(90,250),year=2025)
        run=eager_globals['process'] if eager else X.process
        run(a.c,a.o,[f],'FAKE',fetch=a.fake,now=datetime(2026,11,14))
        a.put(op(350,350,90)); a.put(op(250,250,80,150),r='H1')
        run(a.c,a.o,[am],'FAKE',fetch=a.fake,now=datetime(2026,11,16))
        obs.append(a.q()[0][3:5])
    assert obs==[(100,90),(150,90)]
    save('의존 원자료의 정정·캐시 시점 차이', f"결과 달라짐: 최초 Q3 뒤 H1 누적 200→250, 정정 Q3 누적 350. 필요할 때 수신={obs[0]}, 항상 수신={obs[1]}; 먼저 받은 H1을 재사용하는 차이")
    return results


def migration(snapshot):
    b=ro(snapshot)
    before=b.execute('SELECT * FROM earnings_q ORDER BY ticker,year,reprt').fetchall()
    raw_before=b.execute('SELECT * FROM earnings_raw ORDER BY ticker,year,reprt').fetchall()
    oldcols=[r[1] for r in b.execute('PRAGMA table_info(earnings_raw)')]
    badges_before=X.EF.load('20261009',db=str(snapshot))
    b.close()
    c=X.open_db(str(snapshot))  # explicitly authorized migration of a disposable copy
    after=c.execute('SELECT * FROM earnings_q ORDER BY ticker,year,reprt').fetchall()
    dist=c.execute("SELECT COALESCE(state,'NULL'),COUNT(*) FROM earnings_raw GROUP BY state").fetchall()
    raw_after=c.execute('SELECT '+','.join(oldcols)+' FROM earnings_raw ORDER BY ticker,year,reprt').fetchall()
    pending=c.execute('SELECT COUNT(*) FROM earnings_pending').fetchone()[0]
    null_q=c.execute("SELECT COUNT(*) FROM earnings_raw r WHERE state IS NULL AND NOT EXISTS(SELECT 1 FROM earnings_q q WHERE q.ticker=r.ticker AND q.year=r.year AND q.reprt=r.reprt)").fetchone()[0]
    c.close()
    badges_after=X.EF.load('20261009',db=str(snapshot))
    assert before==after and raw_before==raw_after and badges_before==badges_after
    return dict(q=len(before),raw=len(raw_before),state=dist,pending=pending,no_q=null_q,badge=len(badges_after),oldcols=oldcols)


def item1(snapshot):
    results=earnings_cases(); m=migration(snapshot)
    body=f'''# 2026-10-10 재검토 (실행 {guard()})

요청 두 건을 순서대로 독립 검토. 10/09 공휴일·배치 없음에 대한 사용자 예외 승인으로 실행. 운영 코드·원본 DB·docs 변경 없음. 원본 earnings.db는 SQLite로 열지 않고 파일 사본만 사용. 외부 요청 n=0. 가짜 재무 요청 수와 실제 외부 요청 수를 구분했다. 기술 검증 건수이며 수익·모집단 추정 통계가 아니다.

## 1. 실적 수집기 보강 — **고칠 곳 있음**

기존에 지적한 회복 경로 n=2건은 모두 고쳐졌다. 제공 테스트 n=44체크도 통과했다. 그러나 극단값 원본 뒤 정상 정정본이 삭제되고, 원자료의 빈 필드가 나중에 채워져도 자기 보고서는 다시 받지 않는 경로가 남았다.

### (a)~(d) 가짜 응답·메모리 DB 직접 재현

{md(['사례','직접 확인한 결과'],results)}

### (b) 재현 방법 · 영향 · 고치는 안

1. **극단값 뒤 정정본 유실**: 원본의 차/시총을 0.6으로 보내면 raw.state=extreme, q는 없음. 정상 정정본의 차/시총을 0.0002로 보내도 `amend_no_orig`가 먼저 실행되어 큐에서도 삭제한다. 영향: 정정으로 정상화된 보고서가 영구 누락될 수 있음(n=1 재현). 고치는 안: 최초 원본 접수일·시총을 q의 존재와 별개로 보관하고, extreme도 새 접수번호면 재평가. 정정본이 먼저 왔으면 원본 식별을 기다리는 큐로 유지.
2. **원본/정정 처리 순서**: 목록의 새 정정본을 먼저 처리하고 원본이 큐에만 있으면 정정본을 먼저 삭제한다(n=1). 반대 순서는 저장 뒤 정정 가능(n=1). 재무 API가 이미 최신 정정을 돌려주면 숨겨질 수 있으나 보장하지 않는다. 고치는 안: 목록과 큐를 함께 날짜·접수번호로 정렬하고, 원본 미확인 정정은 최종 폐기하지 않기.
3. **빈 필드가 있는 원자료를 영구 재사용**: 최초 Q3의 전년 칸을 모두 비우고 의존 보고서도 실패시킨 뒤, 다음 날 자기 응답만 정상화하면 `no_values` 반복(n=1). 영향: 자료 보충 뒤에도 회복하지 못하고 최대 n=20회 뒤 폐기. 고치는 안: no_values인 자기 보고서도 간격을 두고 재조회하며 최근 성공 원자료와 실패 상태를 분리.
4. **큐에 영구히 남는가**: 정상 구조에서는 처음 본 뒤 n=45일 초과 또는 tries≥20이면 삭제된다. 성공/완료/극단값/원본 없는 정정도 삭제. 조회 창 밖 보고서는 별도 기록 없이 잃을 수 있다. 예산 대기도 시도 n=0인 채 n=46일 후 삭제된다(n=1 재현). 고치는 안: 예산 대기에는 별도 만료를 적용하고, 실패 만료는 사유와 접수번호를 보존. 목록에 다시 나온 실패 건은 삭제 뒤 다시 삽입되어 시도 수가 초기화될 수 있다.
5. **지속 실패 회사 호출**: CFS와 OFS 모두 실패하면 회사·보고서당 하루 n=2회, 실행 n=20회 누적 n=40회(HTTP 재시도 없음 가정); 지연 재시도는 없다. 의존 보고서가 계속 실패하면 의존 보고서 n=2종에 하루 최대 n=4회가 추가될 수 있다. 고치는 안: 실패 종류에 따른 재조회 간격, 회사/보고서별 호출 잔량 관리.

### (c) 호출·시간 상한과 last_end

예산 대기 n=2건 시험은 last_end를 올리고 목록이 비어도 모두 회복했다. 따라서 **큐에 정상적으로 들어가고 만료·정정 선삭제가 없는 동안** last_end 전진 자체는 누락을 만들지 않았다. 그러나 위 만료/정정 선삭제에는 안전하지 않다. 목록 실패 시에는 last_end를 올리지 않는 분기가 소스에 있다(가짜 main 실행은 하지 않음).

상한은 보고서 시작 전에만 검사한다. max_calls=1에 논리 호출 n=6회, max_seconds=1에 가짜 경과 n=100초를 재현했다. `fetch_json`의 HTTP 재시도 n=3회가 논리 호출 n=1회로 집계된다. list 호출도 처리 상한 밖이고 목록을 받는 시간이 process의 n=600초에 포함되지 않는다. 고치는 안: 목록·CFS/OFS·의존 보고서·HTTP 재시도마다 공통 잔량과 전체 시작 시각을 확인하고, 받은 중간 원자료를 보존한 채 대기시키기. 요청 timeout도 남은 시간으로 제한.

### (d) 필요할 때만 의존 보고서 받기

요청한 형태 n=2종(3개월 칸이 누적과 같음, 전년 3개월이 0)은 같은 초기 캐시·같은 응답에서 항상 수신 방식과 결과가 같았다. 0은 결손이 아니며 그대로 사용했다. 비교 코드는 process 함수를 메모리에서 복제해 의존 수신 조건만 항상 참으로 바꾸었고 원본 파일을 고치지 않았다.

다만 **여러 실행에 걸치면 결과가 달라지는 반례 n=1건**을 재현했다. 최초 Q3는 3개월 값이 온전해 새 방식이 H1을 안 받지만, 항상 수신 방식은 H1 누적 200을 미리 저장한다. 이후 H1 응답 누적이 250으로 바뀌고 정정 Q3가 누적 350을 내면, 새 방식은 이제 받은 H1로 350−250=100, 항상 수신 방식은 옛 캐시로 350−200=150을 기록한다(전년 값 90은 동일). 새 방식이 항상 잘못이라는 뜻은 아니나 패치노트의 무조건적인 '결과 값은 종전과 같다'는 성립하지 않는다. 영향: 의존 보고서의 수신 시점·정정 여부에 따라 배지 입력이 달라질 수 있음. 고치는 안: 의존 원자료도 접수번호·수신 시각을 기록하고, 정정/필드 결손 시 필요한 의존 보고서를 갱신하는 정책을 명시.

### (e) 실제 DB의 사본에서 구조 올리기

- 원본 파일을 바이트 복사한 뒤 사본에만 open_db 사용. raw n={m['raw']}, q n={m['q']:,}, 10/09 배지 n={m['badge']}종목. 기존 q의 모든 열·행, raw의 기존 모든 열·행, 배지 집합 모두 동일.
- raw 상태 분포: {m['state']}. 새 큐 n={m['pending']}. q가 없는 NULL raw n={m['no_q']}행은 의존 보고서도 포함하므로 이 수를 누락 수로 해석할 수 없다.
- 마이그레이션은 기존 q가 `source LIKE 'incr%'`인 키만 ok로 정한다. 원자료와 q의 접수번호 일치를 검증하지 않으며, 나머지 옛 실패 건을 큐로 복원하지 않는다. 따라서 기존 실패 건의 소급 회복 보장은 확인 못 함. 고치는 안: 원본 접수일/보고서 식별 자료를 대조해 완료 여부를 판단하고, 식별 가능한 미완료만 큐로 복원.

### (f) 하루 보고서 n=2,000건 추정

아래는 신규 보고서마다 캐시 없음·목록은 최소 n=20페이지·추가 신규 없음·HTTP 재시도 없음·회사가 매일 응답 가능하다는 **조건부 추정**이다. 응답 시간은 실측하지 않았다. 논리 재무 호출 n=4,000회와 처리 n=600초 중 먼저 닿는 조건이며 실제 HTTP 총량 상한과 다르다.

{md(['형태','재무 논리 호출 총량','호출 상한만의 최소 실행일 수','호출당 0.5초 / 1초 / 2초 가정 시 실행일 수'],[
['전년 3개월 포함·CFS 성공','n=2,000','n=1','n=2 / n=4 / n=7'],
['전년 3개월 포함·OFS만 성공','n=4,000','n=1','n=4 / n=7 / n=14'],
['Q3 의존 n=2종 모두 필요·CFS 성공','n=6,000','n=2','n=5 / n=10 / n=20'],
['Q3 의존 n=2종 모두 필요·OFS만 성공','n=12,000','n=3','n=10 / n=20 / n=40']])}

시간 계산은 ceil(총 호출×가정 응답시간/600), 호출 계산은 ceil(총 호출/4000). 분당 n=600회 속도 제한의 최소 간격 0.1초는 각 가정 시간보다 작다. 실제는 보고서 경계·재사용 캐시·재시도·다른 날 신규·목록 시간 때문에 달라진다. 이 때문에 '하루 이틀 지연'은 항상 보장되지 않는다. n=40실행일이면 달력 n=45일보다 길 수 있어 예산 큐 만료와 충돌한다. 정확한 완료일은 **확인 못 함**.

1번 검토 완료. 2번은 이어서 검토 중.
'''
    guard(); OUT.write_text(body,encoding='utf-8'); print('ITEM1_SAVED',json.dumps(m,ensure_ascii=False))
    return body


def item2(snapshot, body):
    spec=importlib.util.spec_from_file_location('refix_review', ROOT/'research/earnings_mcap_refix_20261007.py')
    R=importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
    cs=[ro(ROOT/'backup'/f'earnings_before_mcap_refix_20261009_{stamp}.db') for stamp in ('122516','151934')]
    cs.append(ro(snapshot)); o=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
    old,first,now=[pd.read_sql_query('SELECT * FROM earnings_q',c) for c in cs]
    for c in cs:c.close()
    namesdf=pd.read_csv(ROOT/'dart_cache/corp_code.csv',dtype=str)
    names=dict(zip(namesdf.stock_code,namesdf.corp_name))
    key=['ticker','year','reprt']; merged=old.merge(now,on=key,suffixes=('_old','_new'),validate='one_to_one')
    assert len(old)==len(now)==len(merged)
    target=merged[merged.source_old.str.contains('shares_jump',regex=False)].copy()
    info={}; events=[]; errors=[]; unknown_keys=[]
    for t in sorted(target.ticker.unique()):
        guard(); steps=R.steps_for(o,t); kinds=[R.classify(o,t,s) for s in steps]; info[t]=(steps,kinds)
        for st,k in zip(steps,kinds):
            d,s0,s1,p1,p0=st
            pre=o.execute('SELECT date,close,volume,shares FROM daily_ohlcv WHERE ticker=? AND date<? AND volume>0 AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1',(t,d)).fetchone()
            post=o.execute('SELECT date,close,volume,shares FROM daily_ohlcv WHERE ticker=? AND date>=? AND volume>0 AND close>0 AND shares>0 ORDER BY date LIMIT 1',(t,d)).fetchone()
            ev=o.execute('SELECT rcept_dt,event_type,report_nm FROM dart_events WHERE ticker=? AND rcept_dt BETWEEN ? AND ? ORDER BY rcept_dt',(t,(datetime.strptime(d,'%Y%m%d')-timedelta(days=120)).strftime('%Y%m%d'),d)).fetchall()
            events.append(dict(t=t,date=d,s0=s0,s1=s1,ratio=s1/s0,p=p1/p0 if p0 and p1 else None,kind=k,pre=pre,post=post,events=ev))
        for r in target[target.ticker==t].itertuples():
            sh,px,dt,n=R.shares_adjusted(o,t,r.rcept_dt_old,steps,kinds)
            if n==-1:unknown_keys.append((t,r.year,r.reprt))
            mc=r.mcap_prev_old if n==-1 else (px*sh if sh is not None else None)
            if mc is None:continue
            su=(r.q_op_old-r.q_op_prev_old)/mc
            if abs(mc/r.mcap_prev_old-1)>=.005 and abs(su)>X.EF.SUE_CAP:mc=r.mcap_prev_old
            errors.append(abs(mc/r.mcap_prev_new-1))
    E=pd.DataFrame(events)
    # Detailed evidence goes to the REPLY; keep terminal output compact.
    print('CLASS_COUNTS',dict(Counter(E.kind)))
    changed=abs(target.mcap_prev_new/target.mcap_prev_old-1)>=.005
    flipped=merged[(merged.sue_old>-.01)&(merged.sue_new<=-.01)].sort_values(['rcept_dt_new','ticker'],ascending=[False,True])
    dates=[d for (d,) in o.execute("SELECT DISTINCT date FROM market_daily WHERE series='KOSPI' AND date<='20261009' ORDER BY date")]
    start,end=dates[-60],dates[-1]
    def badges(df):
        latest=df[(df.rcept_dt>=start)&(df.rcept_dt<=end)&df.sue.notna()].sort_values(['rcept_dt','year','reprt_ord']).drop_duplicates('ticker',keep='last')
        return set(latest[latest.sue<=-.01].ticker)
    b0,b1,b2=map(badges,(old,first,now))
    added=sorted(b2-b0)
    active=flipped[flipped.ticker.isin(added)&(flipped.rcept_dt_new>=start)]
    assert max(errors)<1e-10 and len(active)==15, 'Inputs differ from reviewed 2026-10-09 snapshot'
    assert E.kind.value_counts()['ratio_decrease']==104 and E.kind.value_counts()['unknown']==23
    print('REPRO',len(errors),max(errors),'ROWS',len(target),int(changed.sum()),'BADGES',len(b0),len(b1),len(b2),'ADDED',added)
    # Raw detailed evidence is retained in the REPLY so further interpretation can be appended.
    b=old[old.ticker=='012170'].sort_values(key); c=now[now.ticker=='012170'].sort_values(key)
    equal=b.reset_index(drop=True).equals(c.reset_index(drop=True))
    sample=E[E.kind=='ratio_decrease'].copy()
    sample['distance']=sample.p.map(lambda p:min(abs(p-.7),abs(p-.8),abs(p-1.3)))
    sample=sample.sort_values(['distance','t','date']).head(15)
    def step_table(es):
        return md(['종목','주식수 변화일','주식수 배수','마지막 거래 → 첫 거래','종가 배수','판정'],[
            [e.t+' '+names.get(e.t,''),e.date,f'{e.ratio:.6f}',f'{e.pre[0]} {e.pre[1]:g} → {e.post[0]} {e.post[1]:g}' if e.pre and e.post else '확인 못 함',f'{e.p:.6f}' if pd.notna(e.p) else '확인 못 함',e.kind] for e in es.itertuples()])
    unknown_rows=[]
    for e in E[E.kind=='unknown'].itertuples():
        rows=target[(target.ticker==e.t)&(target.rcept_dt_old<e.date)]
        for r in rows.sort_values('rcept_dt_old',ascending=False).head(1).itertuples():
            lo=(datetime.strptime(r.rcept_dt_old,'%Y%m%d')-timedelta(days=10)).strftime('%Y%m%d')
            p=o.execute('SELECT date,close,shares FROM daily_ohlcv WHERE ticker=? AND date<? AND date>=? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1',(e.t,r.rcept_dt_old,lo)).fetchone()
            if p:
                unknown_rows.append([e.t+' '+names.get(e.t,''),e.date,r.rcept_dt_old,f'{r.mcap_prev_old/1e8:.3f}',f'{p[1]*p[2]/1e8:.3f}',f'{r.mcap_prev_old/(p[1]*p[2]):.4f}',f'{e.p:.6f}' if pd.notna(e.p) else '확인 못 함',','.join(sorted(set(v[1] for v in e.events))) or '없음'])
    active_table=[]; stale=[]; zero_volume_diffs=[]
    for r in active.itertuples():
        st,cl=info[r.ticker]
        evs=[f'{s[0]} 주식수 {s[2]/s[1]:.4f}배 / 거래종가 {s[3]/s[4]:.4f}배 / {k}' for s,k in zip(st,cl) if s[0]>r.rcept_dt_new]
        active_table.append([r.ticker+' '+names.get(r.ticker,''),f'{r.year} {r.reprt} / {r.rcept_dt_new}',f'{r.q_op_prev_new/1e8:.2f} → {r.q_op_new/1e8:.2f}',f'{r.mcap_prev_old/1e8:.2f} → {r.mcap_prev_new/1e8:.2f}',f'{r.sue_old*100:.3f}% → {r.sue_new*100:.3f}%','; '.join(evs)])
        trade=o.execute('SELECT date,close,shares FROM daily_ohlcv WHERE ticker=? AND date<? AND volume>0 AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1',(r.ticker,r.rcept_dt_new)).fetchone()
        px=o.execute('SELECT date,close,shares,volume FROM daily_ohlcv WHERE ticker=? AND date=?',(r.ticker,r.px_dt_new)).fetchone()
        age=(datetime.strptime(r.rcept_dt_new,'%Y%m%d')-datetime.strptime(trade[0],'%Y%m%d')).days if trade else None
        stale.append([r.ticker+' '+names.get(r.ticker,''),r.rcept_dt_new,r.px_dt_new,px[3] if px else '확인 못 함',trade[0] if trade else '확인 못 함',age if age is not None else '확인 못 함','n=10일 초과' if age and age>10 else 'n=10일 이내'])
        if px and px[3]==0 and trade:
            trade_sh=trade[2]
            for s,k in zip(st,cl):
                if s[0]>trade[0] and k in R.RATIO_TYPES:trade_sh*=s[2]/s[1]
            zero_volume_diffs.append(abs(trade[1]*trade_sh/r.mcap_prev_new-1))
    print('PRICE_CHECK',len(stale),'zero_volume',len(zero_volume_diffs),'max_relative_diff',max(zero_volume_diffs))
    body=body.replace('1번 검토 완료. 2번은 이어서 검토 중.','1번 검토 완료.')
    body+=f'''
## 2. 배지 시총 재고정 2차 — **그대로 둬도 됨(이번 수정 범위)**

### 전체 대조

보정 전·1차·지금 q는 각각 n={len(old):,}/{len(first):,}/{len(now):,}행. 원 대상 n={len(target)}행·n={target.ticker.nunique()}종목. n={len(E)}지점 분류 {dict(Counter(E.kind))}. 2차 재계산 n={len(errors)}행의 현재 DB 시총 대비 최대 상대차 {max(errors):.3g}. 변경 n={int(changed.sum())}행. 이는 코드의 적용 재현이며 실제 역사 시총의 정답 증명과 다르다.

표시 창 {start}~{end}의 배지 n={len(b0)} → n={len(b1)} → n={len(b2)}종목, 보정 전 대비 신규 n={len(added)}종목. 전체 과거 신규 배지 n={len(flipped)}행.

### (a) 특정 종목

012170 n={len(b)}행은 모든 열 비교에서 보정 전과 동일={equal}.

{step_table(E[E.t.isin(['012170','183300'])])}

### (b) 감소 지점 n=104 중 요청 범위에 가까운 n=15 표본

종가 배수의 0.7·0.8·1.3까지 최소 절대거리가 작은 순서로 골랐다. 범위 안 표본이 n=15 미만이면 가까운 값을 보충했다. 목적 표본이며 오류율의 무작위 추정이 아니다.

{step_table(sample)}

### (c) 불명 지점 n=23의 손대지 않은 행

불명 사건 때문에 유지된 대상 n={len(unknown_keys)}행. 아래는 지점별 가장 최근 선행 보고서 n={len(unknown_rows)}개 대표값(같은 보고서가 두 지점에 중복될 수 있음). 시점 주식수×종가는 DB 기록상의 단순 비교치이며 수정 여부가 불명인 경우 정답 시총으로 쓰면 안 된다.

{md(['종목','불명 변화일','보고서 접수일','유지 시총 억원','시점 종가×주식수 억원','유지/시점','거래 종가 배수','저장 사건 유형'],unknown_rows)}

### (d) 지금 새 배지 표본 n={len(active_table)}종목

현재 창에서 보정 전 대비 추가된 전 종목이다. 영업이익·시총은 억원, 변화율은 영업이익 차/시총. 각 행의 구체적 이상 여부는 아래 최종 해석에 적는다.

{md(['종목','보고서 / 접수일','전년 → 당기 영업이익','보정 전 → 지금 시총','보정 전 → 지금 차/시총','접수 뒤 사건'],active_table)}

가격 신선도 추가 대조(연구 코드의 직전 거래일이라는 설명과 실제 구현 대조):

{md(['종목','접수일','사용 시세일','사용일 거래량','접수 전 마지막 실제 거래일','달력 경과일','신선도'],stale)}

### 최종 해석 · 재현 방법 · 영향 · 고치는 안

**(a) 확인**: 012170의 n={len(b)}행 복원은 맞다. 다만 이 종목에는 감소 사건 뒤 증가 사건도 있어, 복원에는 뒤의 불명 사건이 적용을 막는 효과도 함께 있다. 183300의 거래 종가는 54,400→27,700원(0.509191배), 주식수는 2.5배다. 미조정 가설은 가격 0.4배, 조정 가설은 1배이며 관측값은 전자 쪽이다. 가격배수×주식수배수=1.272978로 미조정 가설과 양립한다. 따라서 저장 자료와 새 규칙 기준에서 미조정 판정에 반례를 찾지 못했다. 실제 권리락 기준가·조정계수의 별도 원문 검증은 **확인 못 함**.

**(b) 표본 결론**: n=15지점 중 잘못 조정됨으로 갔다고 확정할 사례 n=0. 주식수가 약 0.1~0.333배로 감소했는데 거래 종가는 약 0.7~1.3배인 사례들이므로, 미조정 가격이 주식수와 반대로 뛰었다는 설명보다 조정된 과거 가격이라는 설명에 가깝다. 예를 들어 033170은 주식수 0.2배·종가 1.3배여서 가격×주식수배수=0.26이다. 이 확인은 가설의 상대적 적합성 확인이며 실제 사건별 경제적 조정비율 전수 검증과 다르다. n=15 표본 밖 오류율은 **확인 못 함**.

**(c) 큰 시총 유지가 의심되는 우선 표본 n=4종목**: 파루(043200), 한국첨단소재(062970), 모아라이프플러스(142760), 금호에이치티(214330). 모두 주식수 약 0.5배·거래 종가 약 1.299배다. 5:1 표본의 1.3배와 비슷한 움직임이지만 2:1에서는 두 가설 사이 거리가 좁아 고정된 margin 조건에 걸린다. 과거 가격이 조정된 것이 맞다는 **가정**이면 유지된 대표 시총은 각각 428.076→214.038억, 3426.459→1713.230억, 294.326→147.163억, 2076.328→1038.164억으로 약 2배 과대다. 원문 조정계수 확인이 없어 확정 오류는 **확인 못 함**. 006490은 주식수 0.6배·종가 1.299배여서 두 가설이 더 비슷하므로 같은 확신도로 묶지 않았다.

다른 큰 차이 후보는 한울앤제주(276730, 유지/시점 단순 시총 10.333배), 한국유니온제약(080720, 10.091배), 우양피앤엘(002420, 5.221배), 윙입푸드(900340, 2.828배), 오가닉티코스메틱(900300, 2.645배)다. 이들은 후행 증자·조정계수·거래정지 등이 얽혀 있어 단순 시점 주식수로 바꾸는 것이 옳은지는 **확인 못 함**. 큰 차이만으로 오류라고 단정하지 않았다. 재현은 (c) 표의 단순 시점 시총과 유지 시총 대조. 영향은 과대 시총일 경우 악화 배지가 덜 붙을 가능성. 고치는 안은 불명을 임의 배수로 바꾸지 않고 사건별 조정계수·효력일을 확인한 뒤 해당 행만 별도 교정하는 것.

**(d) 새 배지 전수 표본 n={len(active_table)}종목**: n=15 모두 전년 대비 영업이익 감소가 있고, 후행 주식수 감소를 반영해 시총이 기존의 0.1~0.5배가 되어 −1% 경계를 넘었다. 저장 자료만으로 틀렸다고 확정할 새 배지 n=0. 별도의 원문 재무제표 대조는 **확인 못 함**. 경계에 가장 가까운 주성코퍼레이션(109070)은 −1.102%이므로 시총이 약 10.2% 커지면 배지 경계를 벗어날 수 있어 작은 잔여 오차에도 민감하다.

추가로 n={len(zero_volume_diffs)}종목(국영지앤엠·사조동아원·더라미·윙스풋·우듬지팜)의 저장 시세일 거래량이 0이다. 그러나 실제 마지막 거래는 접수 전 n=4~9일 안이고, 그 실제 거래일 종가·주식수에 같은 후행 조정을 적용한 시총은 현재 값과 최대 상대차 {max(zero_volume_diffs):.3g}로 일치한다. 이번 표본에서는 이 때문에 틀린 배지를 찾지 못했다. 소스의 '직전 거래일' 설명과 달리 `shares_adjusted`의 가격 선택에는 volume>0 조건이 없다. 재현은 위 신선도 표. 영향은 장기 정지 때 복사 시세가 접수 전 n=10일 신선도 검사를 통과할 가능성. 고치는 안은 시세 행 날짜와 마지막 실제 거래일을 따로 확인해 신선도를 판별하는 것(이번 검토에서는 적용하지 않음).

2차 수정의 대상 계산 n={len(errors)}행·012170 복원·183300 판정·새 배지 n=15종목에서 되돌릴 확정 근거를 찾지 못했으므로 **그대로 둬도 됨**으로 판단했다. 이는 불명 n=23지점의 역사 시총까지 정확하다는 보증이 아니다. 전수 경제적 진위는 **확인 못 함**.

## 재현과 한계

- 실행: `python -B tests/test_earnings_incr.py`(n=44체크 통과), `python -B research/handoff/code_20261010_recheck.py 1`, 이어서 같은 코드에 `2`를 인자로 실행. 인자 없이 실행하면 두 항목을 순서대로 다시 쓴다.
- 수집기 main·배치·DART·KIS 실행 없음. 제공된 함수를 가짜 응답으로 호출한 검증이며 실제 외부 요청 n=0. 입력 DB는 읽기 전용, open_db 구조 변경은 삭제되는 사본에만 수행. 임시 사본 삭제 후 보존 산출물은 REPLY와 계산 코드뿐이다.
- 원본 earnings.db SHA-256 전후 동일을 확인했다. 운영 코드·tests·docs는 변경하지 않았다. 적용/등록/채택 제안 없음.
- 같은 저장 자료를 다시 본 사후 검토다. 이미 본 자료라는 한계가 있으며, 새 기간·새 원자료에서 독립 확인한 성과 검증이 아니다. 확인하지 못한 원문·실제 호출 지연·경제적 조정계수는 수치로 추측해 채우지 않았다.

최종 결론: 1번 **고칠 곳 있음** / 2번 **그대로 둬도 됨(이번 수정 범위)**. 남은 요청 항목 없음. 원문 조정계수와 실제 실행시간은 확인 못 함.
'''
    guard(); OUT.write_text(body,encoding='utf-8'); o.close()
    return body


def main():
    guard()
    source=ROOT.parent/'dh-q7m3k-data/earnings.db'
    if Path(str(source)+'-wal').exists() and Path(str(source)+'-wal').stat().st_size:
        raise SystemExit('Live WAL present; file snapshot consistency not established')
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    fd,name=tempfile.mkstemp(prefix='recheck_earnings_',suffix='.db',dir=OUT.parent)
    import os
    os.close(fd); snapshot=Path(name)
    assert snapshot.resolve().parent==OUT.parent.resolve()
    try:
        shutil.copyfile(source,snapshot)
        stage=sys.argv[1] if len(sys.argv)>1 else 'all'
        body=OUT.read_text(encoding='utf-8').split('\n## 2.')[0]+'\n' if stage=='2' else item1(snapshot)
        if stage!='1':body=item2(snapshot,body)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        print('SOURCE_SHA256_UNCHANGED',before)
    finally:
        snapshot.unlink(missing_ok=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
