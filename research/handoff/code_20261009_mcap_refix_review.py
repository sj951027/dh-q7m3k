"""Read-only post-application audit. Writes only the corresponding REPLY.
Does not invoke the reviewed script's main or any collector. No temporary DB.
python research/handoff/code_20261009_mcap_refix_review.py
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from datetime import datetime,timezone,timedelta
import sqlite3,importlib.util
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_name('REPLY_20261009_mcap_refix_review.md')


def guard():
    t=datetime.now(timezone(timedelta(hours=9)))
    if t.weekday()<5 and '20:10'<=t.strftime('%H:%M')<'22:30':
        raise SystemExit('KST batch window')
    return t.isoformat(timespec='seconds')


def ro(p):
    return sqlite3.connect('file:'+str(p.resolve())+'?mode=ro',uri=True)


def table(h,rows):
    return '\n'.join(['| '+' | '.join(map(str,h))+' |','|'+'|'.join(['---']*len(h))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def main():
    started=guard()
    # Import has no operational side effects; main() (including temp DB) is never run.
    spec=importlib.util.spec_from_file_location('reviewed_refix',ROOT/'research/earnings_mcap_refix_20261007.py')
    ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
    b=ro(ROOT/'backup/earnings_before_mcap_refix_20261009_122516.db')
    a=ro(ROOT.parent/'dh-q7m3k-data/earnings.db')
    o=ro(ROOT.parent/'dh-q7m3k-data/ohlcv.db')
    old=pd.read_sql_query('SELECT * FROM earnings_q',b)
    new=pd.read_sql_query('SELECT * FROM earnings_q',a)
    merged=old.merge(new,on=['ticker','year','reprt'],suffixes=('_old','_new'),validate='one_to_one')
    assert len(old)==len(new)==len(merged)
    source=merged.source_old.str.contains('shares_jump',regex=False)
    target=merged[source].copy()
    target['ratio']=target.mcap_prev_new/target.mcap_prev_old
    target['changed']=abs(target.ratio-1)>=.005
    target['flip']=(target.sue_old>-.01)&(target.sue_new<=-.01)
    allchanged=abs(merged.mcap_prev_new/merged.mcap_prev_old-1)>=.005
    assert not (allchanged&~source).any()
    for col in ['rcept_dt','q_op','q_op_prev']:
        assert np.array_equal(merged[col+'_old'],merged[col+'_new'],equal_nan=True) if col!='rcept_dt' else (merged[col+'_old']==merged[col+'_new']).all()
    names={}
    corp=pd.read_csv(ROOT/'dart_cache/corp_code.csv',dtype=str)
    names=dict(zip(corp.stock_code,corp.corp_name))
    step_rows=[];info={};repro=[];identity=[]
    for ticker in sorted(target.ticker.unique()):
        guard()
        st=ref.steps_for(o,ticker);cl=[ref.classify(o,ticker,x) for x in st]
        info[ticker]=(st,cl)
        for step,kind in zip(st,cl):
            date,s0,s1,c1,c0=step
            lo=(datetime.strptime(date,'%Y%m%d')-timedelta(days=120)).strftime('%Y%m%d')
            events=o.execute('SELECT rcept_dt,event_type,report_nm FROM dart_events WHERE ticker=? AND rcept_dt BETWEEN ? AND ? ORDER BY rcept_dt',(ticker,lo,date)).fetchall()
            pre=o.execute('SELECT date,close,volume,shares FROM daily_ohlcv WHERE ticker=? AND date<? AND volume>0 ORDER BY date DESC LIMIT 1',(ticker,date)).fetchone()
            post=o.execute('SELECT date,close,volume,shares FROM daily_ohlcv WHERE ticker=? AND date>=? AND volume>0 ORDER BY date LIMIT 1',(ticker,date)).fetchone()
            step_rows.append(dict(ticker=ticker,date=date,kind=kind,q=s1/s0,p=c1/c0 if c0 else np.nan,events=events,pre=pre,post=post))
        for row in target[target.ticker==ticker].itertuples():
            sh,close,px,n=ref.shares_adjusted(o,ticker,row.rcept_dt_old,st,cl)
            if sh is None:
                continue
            mc=sh*close;sue=(row.q_op_old-row.q_op_prev_old)/mc
            update=abs(mc/row.mcap_prev_old-1)>=.005 and abs(sue)<=.5
            expected=mc if update else row.mcap_prev_old
            repro.append(abs(expected-row.mcap_prev_new)/row.mcap_prev_new)
            identity.append(int(update))
    assert max(repro)<1e-10
    steps=pd.DataFrame(step_rows)
    counts=steps.kind.value_counts()
    bad=target[target.ticker=='012170'].copy()
    assert len(bad)==13 and bad.changed.all()
    raw=o.execute("SELECT date,close,volume,shares FROM daily_ohlcv WHERE ticker='012170' AND date BETWEEN '20260803' AND '20260831' ORDER BY date").fetchall()
    suspect=steps[(steps.kind=='ratio_event')&steps.events.map(lambda ev:any(x[1] in ['paid_in','cb','paid_bonus_mix'] for x in ev))]
    unknown=steps[steps.kind=='unknown']
    # Stratified, deterministic diagnostic sample, including all non-decrease classes first.
    sampled=['012170','183300']
    for ticker in steps[steps.kind!='ratio_decrease'].ticker.unique():
        if ticker not in sampled:sampled.append(ticker)
    sampled=sampled[:30]
    for ticker in sorted(target.ticker.unique()):
        if len(sampled)>=30:break
        if ticker not in sampled:sampled.append(ticker)
    assert len(sampled)==30
    sample_rows=[]
    for ticker in sampled:
        row=target[target.ticker==ticker].sort_values('rcept_dt_old').iloc[-1]
        px=o.execute('SELECT date,close,shares FROM daily_ohlcv WHERE ticker=? AND date<? AND date>=? AND close>0 AND shares>0 ORDER BY date DESC LIMIT 1',(ticker,row.rcept_dt_old,(datetime.strptime(row.rcept_dt_old,'%Y%m%d')-timedelta(days=10)).strftime('%Y%m%d'))).fetchone()
        # Independent data-basis cap, not claimed as an authoritative historical cap.
        observed=px[1]*px[2]
        step=steps[steps.ticker==ticker].iloc[-1]
        pre,post=step.pre,step.post
        tradable=f'{post[1]/pre[1]:.4f}' if pre and post else '확인 못 함'
        sample_rows.append([ticker,names.get(ticker,''),row.rcept_dt_old,px[0],f'{observed/1e8:.3f}',f'{row.mcap_prev_new/1e8:.3f}',f'{row.mcap_prev_new/observed:.4f}',step.kind,tradable])
    # Badge sample evenly across the sorted 322 changed report rows, not only today.
    flips=target[target.flip].sort_values(['ticker','rcept_dt_old'])
    indices=np.linspace(0,len(flips)-1,20).round().astype(int)
    flip_rows=[]
    for row in flips.iloc[indices].itertuples():
        flip_rows.append([row.ticker,names.get(row.ticker,''),str(row.year)+row.reprt,row.rcept_dt_old,
                          f'{row.q_op_prev_old/1e8:+.2f} → {row.q_op_old/1e8:+.2f}',f'{row.mcap_prev_old/1e8:.2f}',f'{row.mcap_prev_new/1e8:.2f}',f'{row.sue_old*100:+.2f} → {row.sue_new*100:+.2f}'])
    # Exactly the display rule, with independent read-only selection.
    calendar=[r[0] for r in o.execute("SELECT DISTINCT date FROM market_daily WHERE series='KOSPI' AND date<=? ORDER BY date",('20261009',))]
    start,end=calendar[-60],calendar[-1]
    def badge(df):
        q=df[(df.rcept_dt>=start)&(df.rcept_dt<=end)&df.sue.notna()].sort_values(['rcept_dt','year','reprt_ord']).drop_duplicates('ticker',keep='last')
        return set(q[q.sue<=-.01].ticker)
    before,after=badge(old),badge(new)
    reversal=pd.DataFrame([dict(ticker=r.ticker,year=r.year,reprt=r.reprt,rcept_dt=r.rcept_dt_old,mcap_prev=r.mcap_prev_old,sue=r.sue_old,q_op=r.q_op_old,q_op_prev=r.q_op_prev_old,reprt_ord=r.reprt_ord_old) for r in bad.itertuples()])
    corrected=new.copy().set_index(['ticker','year','reprt'])
    for row in reversal.itertuples():
        corrected.loc[(row.ticker,row.year,row.reprt),['mcap_prev','sue']]=[row.mcap_prev,row.sue]
    reversed_badges=badge(corrected.reset_index())
    dilution_rows=[]
    for row in steps[steps.kind=='dilution_event'].itertuples():
        px=row.p
        dilution_rows.append([row.ticker,names.get(row.ticker,''),row.date,f'{row.q:.4f}',f'{px:.4f}',f'{(1-1/row.q)*100:.2f}', '확인 못 함'])
    def step_table(df):
        return table(['코드','이름','변화일','분류','주식 수 배수','인접 종가 배수','120일 내 사건 유형'],[[r.ticker,names.get(r.ticker,''),r.date,r.kind,f'{r.q:.6f}',f'{r.p:.6f}',','.join(sorted(set(e[1] for e in r.events))) or '없음'] for r in df.itertuples()])
    sections=['# REPLY — 1. 실적 배지 시총 재고정 사후 검토',
        f'검토 {started}. **결론: 일부 되돌려야 한다. 012170의 이번 보정 13행은 적용 전 상태로 되돌리고 정확한 재계산을 보류할 필요가 있다.** 사용자 지시대로 여기서 멈추며 2~7번은 시작하지 않았다. DB 변경·원 스크립트 main 실행·수집·DART/KIS 호출 없음. 아래의 고치는 안은 제안만이다.',
        '## 실측 요약',
        f'- 전/후 표 {len(old):,}/{len(new):,}행. 원 대상 {len(target):,}행·{target.ticker.nunique()}종목, 시총 변경 {int(target.changed.sum()):,}행. 원 코드의 분류 및 계산을 읽기 전용 함수로 재실행해 전 대상 {len(repro):,}행의 적용 후 값과 대조: 최대 상대차 {max(repro):.3g}. 이는 **구현 재현**이며 경제적 정답 검증과 다르다.\n- 실제 분류 n={len(steps)}지점: '+', '.join(f'{k} {v}' for k,v in counts.items())+'. 요청의 공시 없는 깔끔한 비율 60건·불명3건은 이전 분류 수로 보이며 현재 분류와 다르다. 현행 ratio_clean 4지점·unknown 6지점으로 검토했다.\n'+f'- 배지 신규 {len(flips)}보고서 행. 현재 표시 창 {start}~{end}: {len(before)}→{len(after)}종목, 신규 {len(after-before)}·해제 {len(before-after)}. 012170만 적용 전으로 복원하는 읽기 전용 가상 비교: 표시 {len(reversed_badges)}종목, 현재 대비 해제 {len(after-reversed_badges)}종목. 현재 반기 실적은 개선이라 그 종목의 현 배지는 없지만, 과거 배지 {int(bad.flip.sum())}행이 새로 생겼고 과거 sue 값의 절댓값 전체가 5배 가까이 커졌다.',
        '## 되돌림 근거 — 012170',
        '실측: 20260805 실제 거래 종가 748원·20,250,194주. 이후 정지 중 20260820 주식 수만 4,050,038주로 줄고 종가는 748원 그대로, 20260824 주식 수가 다시 7,296,721주로 증가했고(같은 시기 유상증자 공시 기록), 20260828 재개 종가 3,705원(748원의 4.9532배). 즉 이 저장 구간은 주식 수 감소 전 종가가 같은 기준으로 소급 조정된 연속 가격이라는 전제를 만족하지 않는다. 정지 중 옛 종가의 복사를 가격 연속성 증거로 쓰면 안 된다.',
        table(['날짜','종가 원','거래량 주','기록 주식 수'],raw),
        '**해석:** 정지 중 두 종가가 같다는 사실만 보고 ratio_decrease를 적용한 것은 잘못이다. 20260814 접수분은 전일 종가 748원×20,250,194주=151.47145112억원인데 적용 후 30.29428424억원으로 줄었다(80% 감소). 해당 접수 이전 가격은 이 사건의 역배수로 이미 낮아진 값이 아니다. 13행 모두 같은 추가 1/5 보정을 제거해야 한다. 다만 적용 전 백업 자체도 과거 실제 주식 수의 완전한 정답이라고 확정하지 않는다. 안전한 일시 되돌림과 완전한 역사 시총 복원은 별개다.',
        table(['연도/보고','접수일','옛 시총 억원','새 시총 억원','옛 감소율 %','새 감소율 %','신규 배지'],[[str(r.year)+r.reprt,r.rcept_dt_old,f'{r.mcap_prev_old/1e8:.3f}',f'{r.mcap_prev_new/1e8:.3f}',f'{r.sue_old*100:+.3f}',f'{r.sue_new*100:+.3f}','예' if r.flip else '아니오'] for r in bad.itertuples()]),
        '재현 방법: 위 코드로 정지일 전후 마지막/첫 **거래량 양수일**을 찾고, 20260813의 close·shares 직접 곱과 적용값을 비교. 영향: 012170 13행 시총 80% 과소 및 sue 약 5배 확대, 과거 신규 배지 1행; 현재 표시 배지 종목 수는 변하지 않음. 고치는 안: 이 13개 키의 mcap_prev·sue·shares_at·px_dt·source를 백업 값으로 임시 복원하되, 실행은 사용자/구현 담당자가 수행. 이후 거래정지 중 가격 복사를 제외한 사건 효력일·실제 조정계수를 확인한 뒤 재계산. 전체 1,548행의 일괄 되돌림을 뜻하지 않는다.',
        '## (1) 분류 규칙의 다른 허점',
        f'실측: ratio_event {int((steps.kind=="ratio_event").sum())}지점 중 유상증자·CB·유무상 혼합 공시가 함께 잡히는 지점 {len(suspect)}개. 120일 안에 감자 공시가 있었다는 이유만으로 이후 모든 증가 지점을 비율형으로 분류한다. 같은 공시를 여러 단계에 중복 연결할 수 있다. **해석:** 총 주식 수 증가율은 무상 비율·유상 신주·CB 전환이 섞이면 가격 조정계수와 같지 않다. 실제 각 사건 오분류의 확정은 효력일·발행가·배정비율 부재로 확인 못 함.',
        step_table(suspect),
        '재현 방법: 012340/042040/080720/083660 등에서 앞선 감자 공시와 후속 주식 수 증가 지점을 각각 조회. 영향: 증가 전체를 소급 가격 조정으로 취급해 접수 시총이 달라질 수 있음. 고치는 안: 공시 유형 집합만 보지 말고 사건별 효력일·조정비율을 하나씩 연결하고, 혼합/중복/근거 불명은 검증 보류. 비율이 정확히 정수라는 이유만으로 액면분할로 확정하지 말 것.',
        step_table(steps[steps.kind=='ratio_clean']),
        step_table(unknown),
        'unknown은 명확한 가격 조정계수가 없는데도 max(1, 주식 수 비율)을 적용한다. 이는 과소 배지를 줄이기 위한 보수적 대체 규약일 뿐 정확한 시총 복원이 아니다. 감소 unknown은 1배로 두는 비대칭도 있다. 6지점에 대한 정확한 사건별 오류 크기는 확인 못 함.',
        '183300 참고: 20260811~12 정지 중 종가 54,400→21,800(0.400735배), 주식 수 2.5배. 이 구간도 가격이 연속 조정되었다는 가정과 다르지만 이번 적용 변경은 0행(n=13)이므로 이번 보정의 되돌림 목록에는 넣지 않았다. 이전 자료의 별도 문제다.',
        '## (2) 30종목 독립 진단',
        '표본 n=30종목. 012170·183300을 먼저 넣고 비감소 분류 종목을 코드순으로 채운 고정 진단 표본(무작위 모집단 추정 아님). 각 종목 원 대상 중 최신 접수분의 직전 10일 내 최근 유효 종가×그 행에 기록된 주식 수를 SQL로 직접 구했다. 이것은 **저장값 기준 곱**이며 수정 전 실제 시총이라고 확정하지 않는다. 마지막 열은 마지막 큰 주식 수 사건 전후 거래량 양수일 종가 비율로, 사건일 바로 앞뒤 정지 종가와 구분한다. n=30의 진짜 접수 시총을 모두 확정한 것은 아니다.',
        table(['코드','이름','접수일','시세일','기록 종가×주식수 억원','적용 후 억원','적용/기록곱','마지막 분류','실제 거래 종가 후/전'],sample_rows),
        '## (3) 신규 배지 20건 설명',
        f'신규 n={len(flips)}보고서 행 중 정렬 순서에서 균등 간격으로 n=20건 선택. 영업이익 자체는 전/후 동일하고 시총 분모만 바뀌어 임계값 −1%를 넘었다. 이 표는 배지 변화의 산술 설명이며 시총 정확성에 대한 승인 목록이 아니다. 앞의 012170 반례 때문에 신규 322행 전체를 모두 타당하다고 확인할 수 없다.',
        table(['코드','이름','보고','접수일','영업이익: 전년→당기 억원','옛 시총 억원','새 시총 억원','감소분/시총 옛→새 %'],flip_rows),
        '## (4) 희석형 권리락 무시의 오차',
        '정확한 실측 오차는 **확인 못 함**. 저장 dart_events에는 접수일·제목·사건유형만 있고 발행가·권리락일·가격 조정계수가 없다. 현재 수정종가 하나만으로 원래 비조정 가격을 분리할 수도 없다. 인접 종가 움직임을 곧바로 권리락 할인율이라고 부르지 않았다. 아래 n=10지점의 마지막 수치는 **현금 발행가를 0으로 놓고, 주식 증가 전부가 유상 신주라고 가정한 민감도 상한 1−1/r**이다. 실제 오차 측정치·95% CI가 아니다. CB·발행가·발행 시점이 다르면 이 가정 자체가 안 맞는다.',
        table(['코드','이름','변화일','주식 수 r','인접 종가 후/전','가정상 최대 과소 %','실제 권리락 오차'],dilution_rows),
        '재현 방법: 실제 조정 전/후 동일 날짜 가격이나 권리락 기준가격·발행가가 있어야 비교 가능. 영향: 수정가격에 실제 접수 주식 수를 그대로 곱하면 권리락 계수만큼 시총을 과소·악화율을 과대할 수 있음. 고치는 안: 유상증자도 사건별 실제 조정계수를 적용하고, 자료가 없는 경우 수치를 정확한 접수 시총으로 표시하지 말 것.',
        '## 한계·검증·다음 시작점',
        f'- n={len(repro)}행 적용 재현, n=30종목 저장값 기반 독립 진단, n=20 신규 배지 산술 설명을 완료. 사건별 정확한 역사 시총·혼합 공시 조정비율·희석 권리락 오차는 확인 못 함. 현재 공시 목록만으로 분류 진실을 전부 확정할 수 없다.\n- DB는 세 개 모두 mode=ro. 원 스크립트 main은 임시 복사 DB에 쓰므로 실행하지 않고 읽기 전용 함수만 호출했다. 이 계산은 DB·운영 코드·docs를 변경하지 않는다.\n- 표의 건수·개별 사례·고정 표본은 전수/기술통계이며 95% 표본 구간을 붙이지 않았다. 모집단 성과나 무작위 추정으로 일반화하지 않는다.\n- 사용자 중단 조건에 따라 **1번 완료 후 중단. 다음에 이어서 할 번호는 2번**. 먼저 012170 13행 되돌림 검토를 사용자·구현 담당자에게 전달할 것. 실제 되돌림은 수행하지 않았다.\n- 재현: `python research/handoff/code_20261009_mcap_refix_review.py`. 큰 중간 파일·임시 DB 없음. 산출물은 이 REPLY와 계산 코드 두 파일.']
    guard();OUT.write_text('\n\n'.join(sections)+'\n',encoding='utf-8')
    print('DONE',OUT,'target',len(target),'changed',int(target.changed.sum()),'new_badges',len(flips),'rollback',len(bad),'rollback_badge_rows',int(bad.flip.sum()))


if __name__=='__main__':
    main()
