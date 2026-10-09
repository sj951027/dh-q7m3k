"""Audit frozen discovery outputs; no refit, network, DB writes, or deletion.
Only write REPLY_20261004_discovery.md. Existing summary CSVs are read, not rebuilt.
python research/handoff/code_20261009_discovery_audit.py
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib, json, sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'research/target20_discovery_20261004'
OUT = Path(__file__).with_name('REPLY_20261004_discovery.md')
METHODS = ['learn_hit','learn_first','learn_joint','learn_ret','learn_balanced','cluster_shape',
           'control_amount','control_fundamental','control_rsi']


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and '20:10' <= now.strftime('%H:%M') < '22:30':
        raise SystemExit('KST batch window')
    return now.isoformat()


def block(a, width=20):
    a = np.asarray(a, float)
    assert np.isfinite(a).all() and len(a) > width
    rng = np.random.default_rng(20261003)
    starts = rng.integers(0, len(a)-width+1, (2000, int(np.ceil(len(a)/width))))
    ix = (starts[:,:,None] + np.arange(width)).reshape(2000,-1)[:,:len(a)]
    return np.quantile(a[ix].mean(axis=1), [.025,.975])


def cell(mean, lo, hi):
    return f'{mean:+.3f} [{lo:+.3f}, {hi:+.3f}]'


def estimate(a):
    a = np.asarray(a,float)
    return cell(a.mean(), *block(a))


def tbl(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'] +
                     ['| '+' | '.join(map(str,r))+' |' for r in rows])


def select(df, method):
    if method.startswith('hybrid_'):
        df = df.dropna(subset=['control_fundamental']).sort_values(
            ['date','control_fundamental','amount','ticker'], ascending=[True,False,False,True]).groupby('date').head(50)
        score = 'learn_' + method.removeprefix('hybrid_')
    else:
        score = method
    return df.dropna(subset=[score]).sort_values(['date',score,'amount','ticker'],
             ascending=[True,False,False,True]).groupby('date').head(10).copy()


def main():
    started = guard(); sys.stdout.reconfigure(encoding='utf-8')
    original = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in P.iterdir() if f.is_file() and f.suffix in ['.csv','.json','.md']}
    S=pd.read_csv(P/'summary.csv'); H=pd.read_csv(P/'hybrid_summary.csv')
    D=pd.read_csv(P/'daily_results.csv',dtype={'date':str}); HD=pd.read_csv(P/'hybrid_daily.csv',dtype={'date':str})
    lines=['# REPLY — 2번 데이터 주도 탐색 마무리 (2026-10-09)',
           f'실행 시작 KST {started}. 기존 summary.csv·hybrid_summary.csv를 읽어 사용하며 재생성하지 않는다. 새 계산은 기록 감사·혼합안 시총 대조·주식 수 급변 제외 감도다. 운영·DB·docs 변경, 수집기 실행, 모델 등록, 파일 삭제 없음.',
           '\n## 1. 계획 대비 완료·미완료',
           tbl(['PLAN 항목','현재 상태'],[
               ['149개 입력 후보·초기 관측률 필터','완료: 두 시장 각각 78개 입력 기록. 아래에서 독립 확인'],
               ['분기별 지도학습·군집','완료: 2025Q1~2026Q3 × 2시장, 14개 분기/시장 기록'],
               ['시장별 상위10·대조·시총 구간·분기/연도·40일·집중·확률 진단','기존 산출물 있음. 요약과 한계는 아래'],
               ['재무 상위50→학습 점수 상위10 혼합안','이미 완료: first/joint/ret × 2시장 × 400일. 재학습·재계산하지 않음'],
               ['2024·2025·2026 세 연도 평가','미완료: 2024는 초기 학습, 예측·평가 없음. 기존 계획은 평가를 2025부터로 고정'],
               ['시총 오류 영향','기존 발견 규칙으로 아래에 제외 감도 추가. 역사적 시총 복구·재학습은 안 함'],
               ['보고서','이 REPLY로 완료. 기존 report.py는 실행하지 않음'],
               ['중간 파일 정리','목록과 재생성 경로만 기재. 이번 요청대로 삭제하지 않음']]),
           '\n## 현재까지 확인한 결론',
           '2024 평가가 없어 **세 연도 같은 방향 + 대조 대비 CI가 0을 안 걸침**이라는 요청 기준을 통과했다고 할 수 없다. 이번 결과는 전부 **관측**이다. 혼합안 자체는 이미 끝나 있어 추가 학습이 필요한 상태가 아니다.']
    OUT.write_text('\n\n'.join(lines)+'\n\n감사 진행 중: 아래 계산 완료 뒤 결과를 덧붙인다.\n',encoding='utf-8')
    zpath=ROOT/'research/fullscan_20260903/panel.npz'
    info=json.loads((P/'build_info.json').read_text())
    panel_hash=hashlib.sha256(zpath.read_bytes()).hexdigest()
    assert panel_hash == info['panel_sha256'], 'Panel changed; do not use it for sensitivity'
    z=np.load(zpath,allow_pickle=True); dates=z['dates'].astype(str); tick=z['tick'].astype(str)
    shares=z['shares'].astype(float); ratio=shares[1:]/np.where(shares[:-1]>0,shares[:-1],np.nan)
    flag=np.any((ratio>1.5)|(ratio<1/1.5),axis=0)
    O=pd.read_parquet(P/'outcomes.parquet'); Q=pd.read_parquet(P/'feature_quintiles.parquet',columns=['market_cap','annual_roe','op_yoy'])
    X=pd.read_parquet(P/'raw_features.parquet')
    assert len(O)==len(X)==len(Q)==info['n_rows']
    assert not O.duplicated(['t','j']).any()
    assert (O.date.to_numpy()==dates[O.t.to_numpy()]).all()
    audits=[]; prediction_counts=[]; feature_checks=[]; exposure=[]; sensitivities=[];hybrid_size=[]; checks=[]
    annual=pd.read_csv(P/'annual_availability.csv',dtype={'available_receipt':str})
    assert (np.searchsorted(dates,annual.available_receipt.to_numpy(),side='right')==annual.t.to_numpy()).all()
    assert (dates[annual.t.to_numpy()] > annual.available_receipt.to_numpy()).all()
    # Reconstruct two accounting inputs from saved receipts without running original build.
    expected_roe=np.full(len(O),np.nan); expected_yoy=expected_roe.copy()
    selected_receipt=np.empty(len(O),dtype=object); selected_receipt[:]=''
    for j,g in O.groupby('j'):
        e=annual[annual.j==j].sort_values(['t','year','available_receipt'])
        if e.empty: continue
        e=e[e.year >= e.year.cummax()].drop_duplicates('t',keep='last')
        at=np.searchsorted(e.t.to_numpy(),g.t.to_numpy(),side='right')-1
        valid=at>=0
        ev=e.iloc[np.maximum(at,0)]
        age=(pd.to_datetime(g.date.to_numpy())-pd.to_datetime(ev.available_receipt.to_numpy())).days
        valid &= (age>=0)&(age<=550)
        ni=ev.net_income.to_numpy(dtype='float32'); eq=ev.equity.to_numpy(dtype='float32')
        op=ev.op.to_numpy(dtype='float32'); prev=ev.prev_op.to_numpy(dtype='float32')
        ix=g.index.to_numpy()
        expected_roe[ix]=np.where(valid,ni/np.where(eq>0,eq,np.nan),np.nan)
        expected_yoy[ix]=np.where(valid,(op-prev)/np.where(abs(prev)>0,abs(prev),np.nan),np.nan)
        selected_receipt[ix[valid]]=ev.available_receipt.to_numpy()[valid]
    annual_checks=[]
    for col,exp in [('annual_roe',expected_roe),('op_yoy',expected_yoy)]:
        same=np.isclose(exp,X[col].to_numpy(),rtol=1e-5,atol=1e-6,equal_nan=True)
        annual_checks.append([col,len(same),int((~same).sum())])
        assert same.all(), (col,int((~same).sum()))
    cap=z['close'].astype(float)*shares
    capflat=cap[O.t.to_numpy(),O.j.to_numpy()]
    assert np.allclose(capflat,X.market_cap,rtol=1e-6,equal_nan=True)
    for market in ['kospi','kosdaq']:
        guard()
        mo=O[O.market==market].reset_index(drop=True)
        mx=X[O.market==market].reset_index(drop=True)
        df=pd.read_parquet(P/f'predictions_{market}.parquet')
        assert np.array_equal(df.market.unique(),[market])
        assert (df.ticker.to_numpy()==tick[df.j.to_numpy()]).all()
        quarter=mo.date.str[:4]+'Q'+((mo.date.str[4:6].astype(int)-1)//3+1).astype(str)
        fa=pd.read_csv(P/f'fold_audit_{market}.csv',dtype={'train_last_signal':str,'train_last_outcome':str,'test_first_signal':str,'test_last_signal':str})
        for row in fa.itertuples():
            te=mo[quarter==row.fold]; first=int(te.t.min()); tr=mo[mo.t+20<first]
            assert (len(te),len(tr))==(row.n_test,row.n_train)
            assert dates[int(tr.t.max())+20]==row.train_last_outcome<row.test_first_signal
            pred=df[df.fold==row.fold]
            assert np.array_equal(pred[['t','j']].to_numpy(),te[['t','j']].to_numpy())
            assert dates[int(te.t.max())]==row.test_last_signal
            audits.append([market,row.fold,len(tr),len(te),row.train_last_outcome,row.test_first_signal])
        first=int(mo.loc[quarter=='2025Q1','t'].min()); initial=mo.t+20<first
        coverage=mx[initial].notna().mean(); kept=[f for f in mx if coverage[f]>=.6 and mx.loc[initial,f].nunique()>1]
        saved=pd.read_csv(P/f'learned_inputs_{market}.csv')
        assert kept==saved.feature.tolist()
        feature_checks.append([market,len(kept),sum(f.startswith(('model_','snapshot_','daily_')) for f in kept),int(initial.sum()),int(flag[mo.loc[initial,'j']].sum())])
        prediction_counts.append([market,len(df),df.date.nunique(),df.date.min(),df.date.max()])
        # Fresh diagnostics use frozen predictions. Neither original summaries nor models are rebuilt.
        df['flag']=flag[df.j.to_numpy()]
        clean=df[~df.flag].copy()
        baseline=clean.groupby('date').ret.mean()
        sizebase=clean.groupby(['date','size_bin']).ret.mean()
        ctl=select(clean,'control_amount').groupby('date').ret.mean()
        fund=select(clean,'control_fundamental').groupby('date').ret.mean()
        all_size=df.groupby(['date','size_bin']).ret.mean()
        for method in METHODS+['hybrid_first','hybrid_joint','hybrid_ret']:
            chosen=select(df,method)
            exposure.append([market,method,len(chosen),int(chosen.flag.sum()),f'{chosen.flag.mean():.2%}'])
            if method.startswith('hybrid_'):
                # Confirm saved choice path at a few fixed dates, not regenerate summary.
                ref=HD[(HD.market==market)&(HD.method==method)].set_index('date')
                for d in [df.date.min(), '20260102',df.date.max()]:
                    val=chosen.loc[chosen.date==d,'ret'].mean()
                    assert abs(val-ref.loc[d,'ret'])<1e-5
                    checks.append([market,method,d,float(abs(val-ref.loc[d,'ret']))])
                x=chosen.ret.to_numpy()-all_size.reindex(pd.MultiIndex.from_frame(chosen[['date','size_bin']])).to_numpy()
                byday=pd.Series(x,index=chosen.date).groupby(level=0).mean().sort_index()
                hybrid_size.append([market,method,len(byday),estimate(byday)])
            cp=select(clean,method)
            cp['size_diff']=cp.ret.to_numpy()-sizebase.reindex(pd.MultiIndex.from_frame(cp[['date','size_bin']])).to_numpy()
            daily=cp.groupby('date')[['ret','size_diff']].mean().sort_index()
            for period in ['all','2025','2026']:
                a=daily if period=='all' else daily[daily.index.str.startswith(period)]
                comparator=fund if method.startswith('hybrid_') else ctl
                diff=a.ret-comparator.reindex(a.index)
                sensitivities.append([market,method,period,len(a),estimate(a.ret),estimate(a.size_diff),estimate(diff)])
        print('AUDITED',market,flush=True)
    # Check the price formula on 200 fixed frozen prediction rows (no refit).
    sample=pd.concat([pd.read_parquet(P/f'predictions_{m}.parquet') for m in ['kospi','kosdaq']]).sample(200,random_state=20261009)
    ff=pd.DataFrame(z['close']).ffill().to_numpy(); t=sample.t.to_numpy();j=sample.j.to_numpy()
    ret=(ff[t+20,j]/z['open'][t+1,j]-1-.005)*100
    err=float(np.max(np.abs(ret-sample.ret.to_numpy())))
    assert err<1e-4
    del X
    lines += ['\n## 2. 미래 정보 혼입 점검',
              f'**실측:** 패널 SHA256 `{panel_hash}`가 build_info.json과 일치. {len(O):,}행, {O.date.nunique()}개 신호일({O.date.min()}~{O.date.max()}). 패널 자체는 {dates[0]}~{dates[-1]}. 원자료를 최신 DB로 갈아 끼우지 않았다.',
              tbl(['시장','예측 행','평가 날짜','시작','종료'],prediction_counts),
              '**학습 경계:** 14개 구간의 train/test 행 수·순서·마지막 결과일을 저장된 outcomes에서 직접 다시 세어 전부 일치. 이 연구의 수익 정의는 t+1 시가→t+20 종가이므로 `t+20 < 평가 첫 신호일`이 맞다(1번 연구의 t+1 종가→t+21과 다름).',
              tbl(['시장','분기','학습 행','평가 행','학습 최종 결과일','평가 첫 신호일'],audits),
              tbl(['시장','확정 입력 수','model/snapshot/daily 입력 수','초기 학습 행','급변 종목 초기 학습 행'],feature_checks),
              '입력 선택 60% 관측률·고유값 조건도 초기 학습 자료만으로 재확인했다. 최근 운영 점수·수급이 장기 학습 입력에 들어간 흔적 없음. 군집 표준화·군집 성적은 fit.py상 각 학습 구간만 사용한다(이번에 모델 재학습은 하지 않음).',
              f'**연간 재무:** annual_availability {len(annual):,}행 모두 `접수일보다 엄격히 뒤인 첫 패널 거래일`과 저장 t가 일치. 저장된 접수 이벤트로 annual_roe/op_yoy를 재구성한 결과:',
              tbl(['입력','비교 행','불일치'],annual_checks),
              '원본 build 코드는 보고서·개별 항목의 접수번호 날짜 중 최댓값을 택하고 그 다음 거래일부터 사용한다. 오래된 사업연도가 나중에 최신 연도를 덮지 않으며 550일 초과 재무는 비운다. 따라서 **저장된 접수일 기준으로 앞당겨 쓴 오류는 발견하지 못했다**. 다만 최초 공시 당시 원문 버전과 모든 정정 이력까지 감사한 것은 아니다. 오래된 재무가 뒤늦게 정정되면 보수적으로 이용이 늦어지는 문제도 남는다.',
              '**중요한 사후 선택 한계(코드 확인):** outcomes를 만들 때 다음 날 시가·거래량·상하한가 잠김 여부(`filled`)를 확인한 뒤 남은 행에서 평가 종목 상위10을 고른다. 신호일에 알 수 없는 다음 날 하루 전체 거래량·고저 정보를 후보 선정 전에 사용한다. 또한 마지막 가격은 ffill로 거래정지 구간을 이월한다. 학습 결과일 경계는 지켰지만 **실제 주문 시점의 후보 모집단·체결 가능성을 완전히 재현한 시험은 아니다**. 이번에 원자료를 재구축하거나 결과를 임의 보정하지 않았다.',
              '패널 종목 시장은 원본 생성 코드에서 종목별 마지막 market을 과거 전체에 붙인다. 시장 이전 종목에 과거 시장 분류 오류가 있을 가능성은 남으며 이번에는 이전 이력까지 확인하지 않았다. 상장폐지·과거 전체 투자 가능 종목과 수정주가/주식 수 정합성도 미해결이다.',
              '\n## 3. 대조군 구성과 기존 결과',
              'summary.csv의 ex_ret는 **같은 날짜·같은 시장·결과 기록이 남은 종목군** 평균 대비. size_ex_ret는 여기에 **시장 내 시총 5분위**까지 맞춘 평균 대비이다. 시장을 합쳐 시총 순위를 매기지 않았으므로 E4d의 시장 혼합 오류는 여기서 발견되지 않았다. 단 5분위는 정확한 동일 시총이 아니고 시총 입력 자체가 근사치다.',
              'vs_amount는 같은 날짜·시장 거래대금 상위10과 짝비교하되 시총 구간은 맞추지 않는다. hybrid의 vs_fund도 같은 날짜·시장 재무 상위10 대비로, 재선정 후 시총 구성이 달라질 수 있다. 따라서 각 대조의 의미를 섞지 않는다. 비교군 평균에 선정 종목 자체도 포함되는 방식이다.',
              '아래 수치는 **기존 CSV 직접 인용**. 수익은 순수익 %, 차이는 %p. 구간은 연속20개 평가일 이동 블록 2,000회, 95%, 다중비교 보정 전. n=날짜 수이며 각 방식·시장 all은 400일/4,000선택행이다. 실제 자본 제한 계좌 수익이 아니다.']
    lines += ['수익은 다음 거래일 시가 진입→신호일+20 거래일 종가 평가 후 왕복 비용 0.5%p 차감이다. 공동 사건은 순수익≥20%, 첫날 시가→종가 상승, 최저 종가 수익≥−10%, 보유 종가의 80% 이상이 진입가 위인 조건의 동시 충족이다. 각 날짜의 상위10을 평균한 뒤 날짜에 같은 가중치를 둔다.']
    rows=[]
    for r in S[S.period=='all'].itertuples():
        rows.append([r.market,r.method,r.n_dates,cell(r.ret,r.ret_lo,r.ret_hi),cell(r.vs_amount_ret,r.vs_amount_ret_lo,r.vs_amount_ret_hi),cell(r.size_ex_ret,r.size_ex_ret_lo,r.size_ex_ret_hi)])
    lines += [tbl(['시장','방법','n','20일 수익 95%','거래대금 대조 차이 95%','시장·시총 대조 차이 95%'],rows),
              '6개 학습 방식의 시장·시총 대조 대비 양의 수익 우위는 두 시장 모두 CI가 0을 걸친다. KOSDAQ 군집은 반대로 음의 차이 구간이다. KOSPI 재무 대조의 양의 차이는 관측되지만, 학습기가 그 대조를 개선했다는 뜻이 아니다.',
              '\n## 4. 혼합안은 완료되어 있음 — 사후 탐색',
              '재무 5분위 순위(연간 ROE와 영업이익 증가의 평균) 상위50에서 first/joint/ret 학습 점수로 10개를 다시 고른다. 재무 점수 동점은 거래대금, 그 다음 ticker로 풀므로 엄밀히 연속 재무 순위만의 상위50은 아니다. 계획 말미에 명시된 **초기 결과를 본 뒤 추가한 안**이며 초기 고정 사양처럼 취급하지 않는다.']
    rows=[]
    for r in H[H.period=='all'].itertuples():
        rows.append([r.market,r.method,r.n_dates,cell(r.ret,r.ret_lo,r.ret_hi),cell(r.vs_fund_ret,r.vs_fund_ret_lo,r.vs_fund_ret_hi),cell(r.vs_fund_first,r.vs_fund_first_lo,r.vs_fund_first_hi),cell(r.vs_fund_joint,r.vs_fund_joint_lo,r.vs_fund_joint_hi)])
    lines += [tbl(['시장','혼합안','n','수익 95%','재무 대비 수익 차이 95%','첫날 상승 비율 차이 95%p','공동 사건 비율 차이 95%p'],rows),
              '수익 개선 구간이 전부 양수인 혼합안은 없다. KOSDAQ hybrid_first는 첫날 상승 비율 차이가 양수지만 공동 사건 비율 차이는 음수여서 목적 전체를 개선했다고 말할 수 없다.',
              '보완 실측: 혼합안에서 빠져 있던 같은 날짜·시장·시총 5분위 대조를 저장 예측으로만 추가했다(기존 요약 미수정).',
              tbl(['시장','혼합안','n','시총 대조 대비 수익 차이 95%p'],hybrid_size),
              '\n## 5. 연도별 방향 — 2024는 평가 없음',
              '2024 OOS 결과는 **없음(N/A)**. 계획은 2024를 첫 학습에 쓰고 2025부터 평가하도록 정했다. 지금 2024를 새 시험으로 추가하려면 학습·특성 선택 계획이 바뀌므로 하지 않았다. 아래 2025/2026 방향만으로 “세 연도 통과”라고 부를 수 없다.']
    rows=[]
    for r in S[S.period.isin(['2025','2026'])].itertuples():
        rows.append([r.market,r.method,r.period,r.n_dates,cell(r.ret,r.ret_lo,r.ret_hi),cell(r.size_ex_ret,r.size_ex_ret_lo,r.size_ex_ret_hi)])
    lines += [tbl(['시장','방법','연도','n','수익 95%','시총 대조 차이 95%p'],rows)]
    rows=[]
    for r in H[H.period.isin(['2025','2026'])].itertuples():
        rows.append([r.market,r.method,r.period,r.n_dates,cell(r.vs_fund_ret,r.vs_fund_ret_lo,r.vs_fund_ret_hi)])
    lines += [tbl(['시장','혼합안','연도','n','재무 대비 차이 95%p'],rows),
              '\n## 6. 시총·주식 수 급변 영향',
              f'**실측:** 기존 extended_validate의 정의(패널 인접일 주식 수 비율 >1.5 또는 <1/1.5)를 그대로 적용하면 **{int(flag.sum())}/{len(tick)}종목**이다. “약 140개”를 고정 수로 쓰지 않았다. 이는 병합·분할·증자·기록 오류를 모두 포함할 수 있는 표지이며 확정 오류 목록은 아니다. 전체 미래까지 보고 만든 **사후 감도용 제외**이므로 운영 필터로 쓰면 안 된다.',
              'raw_features.market_cap가 panel close×shares와 일치하는 것은 확인했다. 이는 시총이 정확하다는 검증은 아니다. 급변은 market_cap뿐 아니라 turnover20/60, PE/PB 근사·이익/영업/현금흐름 수익률에도 영향을 줄 수 있다.',
              tbl(['시장','방법','기존 선택 행','급변 종목 행','비중'],exposure),
              '**새 감도 계산:** 기존 학습 점수는 고정하고 급변 종목을 예측 후보·대조 양쪽에서 제외한 뒤 동일 규칙으로 다시 상위10을 선택. 혼합안은 제외 후 재무 상위50부터 재선정했다. 시총 분위 경계는 저장된 것을 유지했다. 따라서 학습 단계의 오염 제거·시총 교정·새 분위 계산은 하지 않은 제한적 감도이다. 아래 차이는 일반 방법=거래대금 대조, 혼합안=재무 대조다.',
              tbl(['시장','방법','기간','n','제외 후 수익 95%','제외 후 시총 대조 차이 95%p','제외 후 직접 대조 차이 95%p'],sensitivities),
              '제외 감도 결론: 전체 기간 n=400에서 학습 6종×2시장과 혼합 3종×2시장, 총 18조합 모두 시장·시총 대조 대비 수익 차이의 95% 하단이 양수가 아니다. 따라서 제외 후에도 양의 우위가 확인되지 않는다는 결론은 같다. 연도별 일부 양의 구간은 통합 결과·2024 부재를 대체하지 않는다.',
              '\n## 7. 추가 진단·구현 검산',
              f'- 저장 예측의 무작위 200행을 원시 시가·종가 경로로 다시 계산: 최대 수익 차이 {err:.8g}%p. 기존 verification.json의 200건 검산과는 다른 표본이다.',
              f'- 혼합안 6개×3개 고정 날짜의 선택 수익을 hybrid_daily와 대조: {len(checks)}건, 최대 차이 {max(r[3] for r in checks):.8g}%p. 기존 summary/hybrid_summary는 재생성하지 않았다.',
              '- 상위10은 연속 날짜별 표본이라 수익 창이 겹친다. 20일 블록은 이를 일부 반영하지만 40일 보조 수익에도 기존 코드가 같은 20일 블록을 써 불확실성을 충분히 반영한다고 단정할 수 없다. 40일 숫자는 참고로만 남긴다.']
    rows=[]
    for r in S[(S.period=='all') & S.method.isin(['learn_joint','learn_first','control_amount','control_fundamental'])].itertuples():
        rows.append([r.market,r.method,r.n_dates40,cell(r.ret40,r.ret40_lo,r.ret40_hi),r.unique_stocks,f'{r.largest_stock_share:.2f}%',f'{r.without_best_stock_ret:+.3f}'])
    lines += [tbl(['시장','방법','40일 n','40일 수익/기존 구간','고유 종목','최대 종목 선택 비중','최대 수익기여 종목 제외 평균(구간 없음)'],rows),
              '마지막 열은 기존 집중 진단의 기술통계이며 CI가 없어 우위 판단에 쓰지 않는다. 분기·신뢰도·학습 중요도 파일도 완성되어 있으나 중요도는 학습 안에서의 분할 이득이고 인과관계/새 검증 결과가 아니다.']
    cal=pd.concat([pd.read_csv(P/f'calibration_{m}.csv') for m in ['kospi','kosdaq']])
    rows=[]
    for (m,target),g in cal.groupby(['market','target']):
        rows.append([m,target,len(g),f'{g.auc.mean():.3f}',f'{g.brier.mean():.3f}',f'{g.baseline_brier.mean():.3f}'])
    lines += [tbl(['시장','목표','분기 수','평균 AUC','평균 Brier','학습평균 대조 Brier'],rows),
              '위 값은 기존 분기 진단의 단순 평균·구간 없는 기술통계다. AUC 0.5는 구별 없음, Brier는 낮을수록 좋다. 정확한 성공확률로 읽거나 통과 근거로 쓰지 않는다.',
              '\n## 8. 못 한 것·의심스러운 점',
              '- 2024 평가 없음 → 요청의 세 연도 통과 여부는 평가 불가. 모든 방식은 **관측**, 통과·채택 모델 없음.',
              '- 학습 경계와 저장 재무 접수일은 맞지만, 다음 날 전체 거래량/고저로 후보를 사전 제거하는 구조는 미래 정보에 따른 모집단 선택이다. 실제 주문 성과로 일반화할 수 없다.',
              '- 주식 수 급변 종목은 제외 감도만 확인. 올바른 역사적 시총 복구, 최초 공시 버전, 상장폐지/시장 이전 처리, 오염 제거 후 재학습은 미실시.',
              '- 혼합안은 사후 가설이고 여러 방법·목표·기간을 비교했다. 95% 구간은 다중검정 보정 전이며 일부 양의 구간만 뽑아 채택할 수 없다.',
              '- 기존 report.py의 “공동 목표를 주목표로 먼저 정했다”는 표현은 PLAN만으로 확인되지 않는다(여러 목표를 병렬 비교하도록 기재). 이 보고서에서는 소급해 주목표를 지정하지 않았다.',
              '\n## 9. 큰 중간 파일과 재생성',
              f'폴더 전체 크기 **{sum(f.stat().st_size for f in P.rglob("*") if f.is_file()):,} bytes** (아래 단위 MiB=2^20 bytes). 50MB 초과. 이번 요청대로 **아무 파일도 삭제하지 않았다**.']
    files=[]
    for f in sorted(P.iterdir()):
        if f.suffix=='.parquet':
            action='원자료 재구축으로 재생성 가능; 아래 원천 보존 확인 뒤 삭제 가능'
            if f.name.startswith('predictions_'):
                action='재학습으로 재생성 가능하나 비용 큼; 3번 후속 비교에 유용하므로 지금 보존 권장'
            files.append([f.name,f'{f.stat().st_size/2**20:.2f}',action])
    lines += [tbl(['파일','MiB','지워도 되는가'],files),
              '보존 우선: PLAN·summary/hybrid_summary·daily/hybrid_daily·selected_predictions.csv.gz·fold_audit·learned_inputs·annual_availability·진단 CSV·build_info/verification·이 REPLY·코드. 원천 panel.npz와 dart_hist.db/당시 보조 DB가 달라지면 완전 동일 재생성이 안 될 수 있다. 현재 입력의 해시는 확인했지만 전체 DB 스냅샷을 새로 만들지는 않았다.',
              '기존 전체 재생성 순서(이번에는 실행하지 않음):\n```powershell\npython research/handoff/code_target20_conditions_build.py --output research/target20_discovery_20261004 --raw\npython research/handoff/code_target20_discovery_fit.py kospi\npython research/handoff/code_target20_discovery_fit.py kosdaq\npython research/handoff/code_target20_discovery_evaluate.py\npython research/handoff/code_target20_discovery_hybrid.py\n```',
              '\n## 제안',
              '- 후속 연구에서는 후보 선정 시점과 체결 실패 처리부터 분리해, 다음 날 정보로 후보를 미리 제거하지 않는 평가를 먼저 설계할 필요가 있다. 이번에 기존 코드나 계획을 고치지는 않았다.',
              '\n## 종료·다음 시작점',
              '- 감사 재현: `python research/handoff/code_20261009_discovery_audit.py`. 저장 요약을 읽고 감사·제외 감도만 계산하여 이 REPLY를 쓴다. 큰 새 중간 파일 없음.',
              '- 2번 보고서 작성 완료. 3번은 시작하지 않았다. 사용자가 “다음”이라고 하면 세션 지시서 3번으로 진행하며, 2024 평가 부재·후보 사후 선택·시총 근사 한계를 이어받는다.']
    assert original == {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in P.iterdir() if f.is_file() and f.suffix in ['.csv','.json','.md']}
    guard();OUT.write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    print('DONE',OUT,'flag',int(flag.sum()),'annual',annual_checks,'max_return_error',err)


if __name__=='__main__':
    main()
