"""Offline reconstruction of control_fundamental. Only writes the named REPLY.

python research/handoff/code_20261009_kospi_fundamental_clean.py --baseline-only
python research/handoff/code_20261009_kospi_fundamental_clean.py
No production imports, network calls, DB access, or persisted intermediates.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys, json, hashlib, warnings
import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore', category=RuntimeWarning)
ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'research/target20_discovery_20261004'
OUT = Path(__file__).with_name('REPLY_20261009_kospi_fundamental_clean.md')
SEED = 20261009
H = 20


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and '20:10' <= now.strftime('%H:%M') < '22:30':
        raise SystemExit('KST batch window: no execution or write')
    return now.isoformat(timespec='seconds')


def roll(a, n, minp, fn='mean'):
    return getattr(pd.DataFrame(a).rolling(n, min_periods=minp), fn)().to_numpy()


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(map(str, headers)) + ' |',
                      '|' + '|'.join(['---'] * len(headers)) + '|'] +
                     ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows])


def block_idx(n, h=20, k=2000, seed=20261003):
    if n <= h:
        return None
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n-h+1, (k, int(np.ceil(n/h))))
    return (starts[:, :, None] + np.arange(h)).reshape(k, -1)[:, :n]


def estimate(a, ix=None):
    a = np.asarray(a, float)
    if ix is None:
        ix = block_idx(len(a))
    if ix is None:
        return float(np.nanmean(a)), np.nan, np.nan
    lo, hi = np.nanquantile(np.nanmean(a[ix], axis=1), [.025, .975])
    return float(np.nanmean(a)), float(lo), float(hi)


def cell(a):
    v, lo, hi = a
    return f'{v:+.3f} [{lo:+.3f}, {hi:+.3f}]'


class Reconstruction:
    def __init__(self):
        guard()
        panel = ROOT/'research/fullscan_20260903/panel.npz'
        self.sha = hashlib.file_digest(panel.open('rb'), 'sha256').hexdigest()
        assert self.sha == json.loads((P/'build_info.json').read_text())['panel_sha256']
        z = np.load(panel, allow_pickle=True)
        self.d = z['dates'].astype(str)
        self.tick = z['tick'].astype(str)
        self.mk = np.char.lower(z['mk'].astype(str))
        self.c, self.o, self.h, self.l, self.v = [z[k].astype(float) for k in ['close','open','high','low','vol']]
        self.sh = z['shares'].astype(float)
        self.susp = z['susp']
        self.T, self.N = self.c.shape
        self.ff = pd.DataFrame(self.c).ffill().to_numpy()
        self.idx = np.array([pd.Series(z[k]).ffill().to_numpy() for k in ['kospi','kosdaq']]).T
        r = np.full(self.c.shape, np.nan)
        r[1:] = self.c[1:]/self.c[:-1]-1
        r[~np.isfinite(r)] = np.nan
        self.r = r
        amt = self.c*self.v
        self.ok = ((roll((np.abs(r)<1e-9).astype(float),63,20)<=.5) &
                   (roll((np.abs(r)>.32).astype(float),21,5,'max')<=0) &
                   (roll(r,21,15,'std')>=.003) & (roll(amt,20,10)>=5e8) &
                   (self.susp==0) & (self.c>=1000) &
                   (roll(np.isfinite(self.c).astype(float),252,1,'sum')>=120))
        self.amount = np.log(roll(amt,20,15)).astype('float32')
        self.start = int(np.searchsorted(self.d, '20240102'))
        self.stop = self.T-26   # exact original end, not an extended window
        self.ts = np.arange(self.start, self.stop)
        annual = pd.read_csv(P/'annual_availability.csv')
        assert (np.searchsorted(self.d, annual.available_receipt.astype(str), side='right') == annual.t).all()
        arrays = [np.full(self.c.shape,np.nan,dtype='float32') for _ in range(4)]
        age = np.full(self.c.shape,np.nan,dtype='float32')
        for j,g in annual.groupby('j'):
            latest = -1
            # Original tuple sort includes year, receipt and numeric fields.
            for row in sorted(g.itertuples(index=False,name=None)):
                t, _, year, receipt, ni, eq, assets, revenue, op, ocf, prevop = row
                t=int(t); j=int(j)
                if year < latest:
                    continue
                latest=year
                for a,value in zip(arrays,[ni,eq,op,prevop]):
                    a[t:,j]=value
                age[t:,j]=(pd.to_datetime(self.d[t:])-pd.Timestamp(str(int(receipt)))).days
        ni,eq,op,prevop=arrays
        known=(age<=550)&(age>=0)
        self.roe=np.where(known,ni/np.where(eq>0,eq,np.nan),np.nan).astype('float32')
        self.yoy=np.where(known,np.where(abs(prevop)>0,(op-prevop)/abs(prevop),np.nan),np.nan).astype('float32')
        self.cap=self.c*self.sh
        self.qroe, self.qyoy, self.size = [self.quintile(a) for a in [self.roe,self.yoy,self.cap.astype('float32')]]
        self.score=(self.qroe+self.qyoy)/2
        self.score[(self.qroe==0)|(self.qyoy==0)]=np.nan
        self.filled=np.zeros(self.c.shape,bool)
        self.raw=np.full(self.c.shape,np.nan)
        self.ret=np.zeros(self.c.shape)
        self.valid=np.zeros(self.c.shape,bool)
        for t in self.ts:
            base=self.o[t+1]
            locked=(abs(self.h[t+1]-self.l[t+1])<1e-8)&(abs(base/self.c[t]-1)>=.295)
            f=np.isfinite(base)&(base>0)&(self.v[t+1]>0)&~locked
            raw=self.ff[t+20]/np.where(f,base,np.nan)-1
            self.filled[t]=f
            self.raw[t]=raw
            self.ret[t]=np.where(f,(raw-.005)*100,0)
            self.valid[t]=self.ok[t]&f&np.isfinite(raw)
        # c excludes all limit closes, not only fully locked signal-day bars.
        # Match original .295 daily approximation; no unavailable exchange limit table.
        self.signal_exclude=(self.susp!=0)|(self.v<=0)|(abs(self.r)>=.295)
        self.picks={}
        print('REBUILT',self.c.shape,self.d[self.start],self.d[self.stop-1],flush=True)

    def quintile(self,a):
        q=np.zeros(self.c.shape,dtype='uint8')
        for m in ['kospi','kosdaq']:
            mask=self.ok&(self.mk==m)[None,:]
            ranks=pd.DataFrame(np.where(mask,a,np.nan)).rank(axis=1,pct=True).to_numpy()
            q=np.where(np.isfinite(ranks),np.ceil(ranks*5).clip(1,5),q).astype('uint8')
        return q

    def population(self,t,m,mode,exclude=None):
        mask=self.ok[t]&(self.mk==m)
        if mode=='a':
            mask=mask&self.valid[t]
        elif mode=='c':
            mask=mask&~self.signal_exclude[t]
        if exclude is not None:
            mask=mask&~exclude
        return np.flatnonzero(mask)

    def choose(self,t,m,mode,exclude=None,rng=None):
        js=self.population(t,m,mode,exclude)
        js=js[np.isfinite(self.score[t,js])]
        if rng is None:
            order=np.lexsort((self.tick[js],-self.amount[t,js],-self.score[t,js]))
        else:
            order=np.lexsort((rng.random(len(js)),-self.score[t,js]))
        return js[order[:10]]

    def daily(self,m,mode,exclude=None,rng=None):
        rows=[]; picks=[]
        for t in self.ts:
            pop=self.population(t,m,mode,exclude)
            js=self.choose(t,m,mode,exclude,rng)
            assert len(js)==10
            size_base=np.array([np.mean(self.ret[t,pop[self.size[t,pop]==q]]) if np.any(self.size[t,pop]==q) else np.nan for q in range(1,6)])
            assert np.isfinite(self.ret[t,pop]).all()
            ret=self.ret[t,js].sum()/10
            sb=size_base[self.size[t,js]-1].sum()/10
            rows.append([t,self.d[t],ret,ret-sb,int((~self.filled[t,js]).sum()),len(pop),int((~self.filled[t,pop]).sum())])
            picks.append(js)
        return pd.DataFrame(rows,columns=['t','date','ret','ex','unfilled','n_pop','pop_unfilled']),picks

    def baseline(self):
        rows=[]; checks=[]
        summary=pd.read_csv(P/'summary.csv')
        old_daily=pd.read_csv(P/'daily_results.csv',dtype={'date':str})
        passed=True
        for m in ['kospi','kosdaq']:
            d,picks=self.daily(m,'a')
            self.picks[m,'a']=picks
            s=d[d.date>='20250101']
            target=summary[(summary.market==m)&(summary.method=='control_fundamental')&(summary.period=='all')].iloc[0]
            own=[s.ret.mean(),s.ex.mean()]
            delta=np.array(own)-[target.ret,target.size_ex_ret]
            old=old_daily[(old_daily.market==m)&(old_daily.method=='control_fundamental')].set_index('date').reindex(s.date)
            day_error=max(np.max(abs(s.ret.to_numpy()-old.ret.to_numpy())),np.max(abs(s.ex.to_numpy()-old.size_ex_ret.to_numpy())))
            pred=pd.read_parquet(P/f'predictions_{m}.parquet')
            tt,jj=pred.t.to_numpy(int),pred.j.to_numpy(int)
            feature_errors=[float(np.nanmax(abs(self.score[tt,jj]-pred.control_fundamental))),float(np.max(abs(self.amount[tt,jj]-pred.amount))),int(np.sum(self.size[tt,jj]!=pred.size_bin))]
            stored=pred.dropna(subset=['control_fundamental']).sort_values(['date','control_fundamental','amount','ticker'],ascending=[True,False,False,True]).groupby('date').head(10)
            stored_map={date:g.j.to_numpy(int) for date,g in stored.groupby('date')}
            mismatch=sum(not np.array_equal(picks[int(t)-self.start],stored_map[date]) for t,date in zip(s.t,s.date))
            ok=(np.max(abs(delta))<1e-4 and day_error<1e-4 and mismatch==0 and max(feature_errors)==0 and len(s)==int(target.n_dates))
            passed=passed and ok
            rows.append([m,len(s),f'{own[0]:+.9f}',f'{target.ret:+.9f}',f'{own[1]:+.9f}',f'{target.size_ex_ret:+.9f}',f'{np.max(abs(delta)):.3g}','일치' if ok else '불일치'])
            checks.append([m,len(pred),*feature_errors,mismatch,f'{day_error:.3g}'])
        section=['## 선행 검증 — 기존 ⓐ 재현',
                 '실측. summary.csv의 전체는 **2025~2026, 400신호일**이다. 아래는 그 기간으로 먼저 맞댄 결과다. 허용 오차 0.0001%p; 모든 날짜 선택 명단도 대조한다. 수익은 다음 날 시가→20번째 날 종가, 체결 건에만 왕복 0.5%p 차감. 일별 상위10 수익의 날짜 평균이며 계좌 수익이 아니다.',
                 table(['시장','n 날짜','새 코드 수익 %','기존 수익 %','새 코드 시총 대비 %p','기존 시총 대비 %p','최대 평균 차이 %p','판정'],rows),
                 table(['시장','기존 후보 행','재무점수 최대차','거래대금 최대차','시총분위 불일치','선택 불일치 날짜','일별 최대차 %p'],checks)]
        outcomes=pd.read_parquet(P/'outcomes.parquet',columns=['t','j'])
        q=pd.read_parquet(P/'feature_quintiles.parquet',columns=['annual_roe','op_yoy','market_cap'])
        absolute=pd.read_parquet(P/'absolute_values.parquet',columns=['annual_roe','op_yoy'])
        tt,jj=outcomes.t.to_numpy(int),outcomes.j.to_numpy(int)
        rebuilt_t,rebuilt_j=np.where(self.valid)
        population_ok=np.array_equal(tt,rebuilt_t) and np.array_equal(jj,rebuilt_j)
        qdiff=[int(np.sum(a[tt,jj]!=q[col])) for a,col in [(self.qroe,'annual_roe'),(self.qyoy,'op_yoy'),(self.size,'market_cap')]]
        adiff=[float(np.nanmax(abs(a[tt,jj]-absolute[col].to_numpy()))) for a,col in [(self.roe,'annual_roe'),(self.yoy,'op_yoy')]]
        passed=passed and population_ok and max(qdiff)==0 and max(adiff)==0
        section.append(f'2024 포함 전체 기존 {len(outcomes):,}행도 검산: 후보 t/j 순서 일치={population_ok}, ROE/영업이익증가/시총 분위 불일치={qdiff}, 재무 원값 최대차={adiff}. 패널 SHA256 `{self.sha}`; 원 build_info와 일치. 접수일 다음 패널 거래일 시작도 모든 재무 이벤트에서 일치.')
        return passed,section

    def share_flags(self):
        ratio=self.sh[1:]/self.sh[:-1]
        return np.any((ratio>1.5)|(ratio<1/1.5),axis=0)

    def account(self,m,mode,exclude=None):
        """20 separately funded accounts, buy next open, liquidate day 20 close.

        10% budget per intended slot including buy fee. Buy-and-hold share
        quantities, cash at zero interest. Sell fee on marked asset value.
        Early/late boundary cash included so all accounts share one calendar.
        """
        guard()
        fee=.0025
        days=np.arange(self.start+1,self.stop+20)
        nav=np.ones((20,len(days)))
        cash_nav=np.ones_like(nav)
        counts={'trades':0,'unfilled':0,'exit_missing':0,'exit_zero_volume':0,'exit_locked':0}
        for offset in range(20):
            wealth=1.
            last=0
            for t in range(self.start+offset,self.stop,20):
                js=self.choose(t,m,mode,exclude)
                f=self.filled[t,js]
                counts['trades']+=int(f.sum());counts['unfilled']+=int((~f).sum())
                ix=js[f]
                values=self.ff[t+1:t+21,ix]/self.o[t+1,ix]
                amounts=values/(10*(1+fee))
                cash=(10-len(ix))/10
                rel=cash+amounts.sum(axis=1)
                rel[-1]=cash+amounts[-1].sum()*(1-fee)
                lo=t+1-days[0];hi=lo+20
                nav[offset,last:lo]=wealth
                cash_nav[offset,last:lo]=wealth
                nav[offset,lo:hi]=wealth*rel
                cash_nav[offset,lo:hi]=wealth*cash
                cash_nav[offset,hi-1]=wealth*rel[-1]
                wealth*=rel[-1];last=hi
                counts['exit_missing']+=int((~np.isfinite(self.c[t+20,ix])).sum())
                counts['exit_zero_volume']+=int((self.v[t+20,ix]<=0).sum())
                counts['exit_locked']+=int(((abs(self.h[t+20,ix]-self.l[t+20,ix])<1e-8)&(abs(self.r[t+20,ix])>=.295)).sum())
            nav[offset,last:]=wealth
            cash_nav[offset,last:]=wealth
        aggregate=nav.mean(axis=0)
        r=aggregate/np.r_[1,aggregate[:-1]]-1
        individual=nav/np.column_stack([np.ones(20),nav[:,:-1]])-1
        mi=0 if m=='kospi' else 1
        bench=self.idx[days,mi]/self.idx[days-1,mi]-1
        assert np.isfinite(r).all() and np.isfinite(bench).all()
        counts['cash_series']=cash_nav.sum(axis=0)/nav.sum(axis=0)*100
        return days,r,bench,individual,nav,counts

    def tie_draws(self,m,mode,exclude=None,k=200):
        """Randomize only the score group straddling position 10."""
        rng=np.random.default_rng(SEED+(m=='kosdaq'))
        rets=np.empty((k,len(self.ts)));exs=np.empty_like(rets)
        n_tie=n_boundary=0;boundary_sizes=[]
        for col,t in enumerate(self.ts):
            pop=self.population(t,m,mode,exclude)
            js=pop[np.isfinite(self.score[t,pop])]
            scores=self.score[t,js]
            cutoff=np.sort(scores)[-10]
            above=js[scores>cutoff];tie=js[scores==cutoff];take=10-len(above)
            assert len(above)+take==10 and 1<=take<=len(tie)
            base=np.array([self.ret[t,pop[self.size[t,pop]==q]].mean() for q in range(1,6)])
            excess=self.ret[t]-base[self.size[t].clip(1,5)-1]
            n_tie+=int(len(tie)>1)
            if len(tie)>take:
                n_boundary+=1
            boundary_sizes.append(len(tie))
            # Independent without-replacement samples within the cutoff group.
            random=rng.random((k,len(tie)))
            positions=np.argpartition(random,take-1,axis=1)[:,:take]
            chosen=tie[positions]
            rets[:,col]=(self.ret[t,above].sum()+self.ret[t,chosen].sum(axis=1))/10
            exs[:,col]=(excess[above].sum()+excess[chosen].sum(axis=1))/10
            for vals,samples in [(self.ret[t],rets[:,col]),(excess,exs[:,col])]:
                ordered=np.sort(vals[tie])
                lower=(vals[above].sum()+ordered[:take].sum())/10
                upper=(vals[above].sum()+ordered[-take:].sum())/10
                assert samples.min()>=lower-1e-9 and samples.max()<=upper+1e-9
        return rets,exs,n_tie,n_boundary,boundary_sizes


PERIODS=['2024','2025','2026','2025-26','all']
LABEL={'a':'ⓐ 사후 필터','b':'ⓑ 상위10→현금','c':'ⓒ 신호일 제외→현금'}


def period_mask(d,period):
    a=np.asarray(d).astype(str)
    return np.ones(len(a),bool) if period=='all' else a>='20250101' if period=='2025-26' else np.char.startswith(a,period)


def stage1(s,sections,save):
    datasets={}
    rows=[];comparison=[];candidates=[]
    for m in ['kospi','kosdaq']:
        for mode in ['a','b','c']:
            guard();d,picks=s.daily(m,mode)
            datasets[m,mode]=d,picks
            sub=d[d.date>='20250101']
            rows.append([m,LABEL[mode],len(sub),10*len(sub),int(sub.unfilled.sum()),f'{100*sub.unfilled.sum()/(10*len(sub)):.3f}',cell(estimate(sub.ret)),cell(estimate(sub.ex))])
            candidates.append([m,LABEL[mode],int(sub.n_pop.sum()),int(sub.pop_unfilled.sum()),f'{100*sub.pop_unfilled.sum()/sub.n_pop.sum():.4f}'])
        b=datasets[m,'b'][1];c=datasets[m,'c'][1]
        different=[i for i in range(len(b)) if not np.array_equal(b[i],c[i])]
        comparison.append([m,len(b),len(different),sum(len(set(b[i])-set(c[i])) for i in different)])
    sections.extend(['## 1. 후보 선정·체결 분리',
        'ⓐ는 신호일 유니버스에서 다음 날 체결 가능·20일 종료가격 가용인 행을 먼저 남기고 상위10. ⓑ는 신호일 점수만으로 상위10 확정. ⓒ는 신호일 정지·거래량 0·상/하한가 마감 표지를 제외하고 상위10 확정. ⓑ·ⓒ 모두 다음 날 못 산 자리 수익 0, 비용 0; 다음 순위로 사후 충원하지 않는다. 10자리 고정 분모다.',
        '상/하한가 표지는 기존 경로와 같은 ±29.5% 근사다. 신호일에는 종가/전일종가, 다음 날 미체결에는 고가=저가이면서 시가/신호일종가 ±29.5%를 사용한다. 실제 거래소 가격제한 값이나 시가 호가·체결 자료가 없으므로 실제 주문 재현은 아니다. 기존 체결 정의에는 다음 날 정지 플래그를 별도로 더하지 않고 거래량 0으로 처리한다.',
        '**기존 비교 기간 2025~2026**. 수익 %, 차이 %p, 현금은 미체결 **예정 자리 비율**(20일 동안의 계좌 현금 비중과 다름). [ ]는 20신호일 이동블록 2,000회 95% 구간.',
        table(['시장','선정','n 날짜','예정 자리','미체결','현금 %','20일 순수익 95%','시총 대조 차이 95%'],rows),
        '대조군 분모는 같은 날·시장·신호일 시총 5분위의 **모든 신호일 적격 종목**이다(재무 결측도 포함). ⓐ만 기존 체결 필터를 적용, ⓑ는 미체결 0 포함, ⓒ는 신호일 제외 후 미체결 0 포함. 선택 10자리의 시총 분위 구성으로 각 분위 평균을 가중한다. 선택 종목도 대조 평균에 포함하는 기존 규약을 유지한다.',
        table(['시장','선정','2025~26 대조 후보-날짜 행','그중 미체결','미체결 %'],candidates),
        table(['시장','2024~26 n 날짜','ⓑ/ⓒ 명단 다른 날짜','다른 예정 자리 합계'],comparison),
        '신호일 유니버스 자체가 정지 종목을 이미 제외한다. 나머지 추가 제외가 명단을 바꾸는지 위에 실측했으며, 임의 조건은 추가하지 않았다.'])
    save('1 완료. 2~6 미완료.')
    print('STAGE 1 SAVED',flush=True)
    return datasets


def result_rows(datasets,periods=PERIODS,prefix=None):
    rows=[]
    for (m,mode),value in datasets.items():
        d=value[0]
        for period in periods:
            sub=d[period_mask(d.date,period)]
            rows.append([m,LABEL[mode],*([prefix] if prefix else []),period,len(sub),10*len(sub),int(sub.unfilled.sum()),int(sub.n_pop.sum()),cell(estimate(sub.ret)),cell(estimate(sub.ex))])
    return rows


def stage2(s,datasets,sections,save):
    sections.extend(['## 2. 연도별·전체와 시총 대조',
        f'신호일 **{s.d[s.start]}~{s.d[s.stop-1]}**, {len(s.ts)}일. 2024는 학습 없는 규칙으로 추가 평가, 2025~26은 기존 400일 비교 창이다. 전체는 2024~26을 뜻한다. 종료일은 기존 build_info와 동일하며 임의 연장하지 않았다. 연도는 신호일 기준, 종료 수익이 다음 연도로 넘어가도 해당 신호 연도에 포함한다.',
        table(['시장','선정','기간','n 날짜','예정 자리','미체결','대조 후보-날짜 행','20일 순수익 % 95%','시총 대조 차이 %p 95%'],result_rows(datasets)),
        '날짜당 10자리 평균을 다시 날짜별 동일가중으로 평균. 20일 결과 창의 겹침을 고려해 연속 20신호일 이동블록 재추출(2,000회, seed=20261003), 연도별로 다시 재추출한다. 시총 분위 경계·재무 분위는 항상 원 신호일 전체 유니버스 기준으로 고정한다. 구간은 다중 비교 보정 전이며 다른 독립 표본의 구간이 아니다.'])
    save('1~2 완료. 3~6 미완료.')
    print('STAGE 2 SAVED',flush=True)


def stage3(s,sections,save):
    flag=s.share_flags()
    assert flag.sum()==152
    data={};exposure=[]
    for m in ['kospi','kosdaq']:
        for mode in ['a','b','c']:
            data[m,mode]=s.daily(m,mode,flag)
            picks=[s.choose(t,m,mode) for t in s.ts]
            n=sum(int(flag[ix].sum()) for ix in picks)
            exposure.append([m,LABEL[mode],10*len(picks),n,f'{n/(10*len(picks))*100:.3f}'])
    sections.extend(['## 3. 주식 수 급변 제외 감도',
        f'실측: 패널 전체 인접 주식 수 비율 >1.5 또는 <1/1.5 표지는 **{flag.sum()}/{s.N}종목**. 병합·분할·증자·기록 오류를 구분한 목록이 아니다. 미래 전체로 만든 **사후 제외 감도**이며 당시 알 수 있던 필터로 해석하지 않는다. 아래는 후보와 대조 양쪽에서 제외하고 상위10 재선정. 재무점수·시총 분위 경계는 그대로 유지한다.',
        table(['시장','선정','전체 예정 자리','급변 표지 자리','비중 % (기술통계)'],exposure),
        '포함 결과는 2절, 제외 결과는 아래. 별도의 시총 복원·주식 수 교정은 하지 않았다.',
        table(['시장','선정','감도','기간','n 날짜','예정 자리','미체결','대조 후보-날짜 행','제외 후 순수익 % 95%','시총 대조 차이 %p 95%'],result_rows(data,prefix='152종목 제외'))])
    save('1~3 완료. 4~6 미완료.')
    print('STAGE 3 SAVED',flush=True)
    return flag,data


def capture(x,b,unit):
    if unit==20:
        n=len(x)//20
        x=np.prod(1+x[:n*20].reshape(n,20),axis=1)-1
        b=np.prod(1+b[:n*20].reshape(n,20),axis=1)-1
        rng=np.random.default_rng(SEED)
        ix=rng.integers(0,n,(2000,n))
    else:
        ix=block_idx(len(x),20,2000,SEED)
    rows=[]
    for name,mask in [('상승',b>0),('하락',b<=0)]:
        count=int(mask.sum())
        ratio=np.mean(x[mask])/np.mean(b[mask]) if count and abs(np.mean(b[mask]))>1e-12 else np.nan
        if count<3 or ix is None:
            bounds='계산 불가 (해당 부호 n<3)'
        else:
            masks=(b[ix]>0) if name=='상승' else (b[ix]<=0)
            nums=np.where(masks,x[ix],np.nan);dens=np.where(masks,b[ix],np.nan)
            rb=np.nanmean(nums,axis=1)/np.nanmean(dens,axis=1)
            rb[masks.sum(axis=1)<3]=np.nan
            lo,hi=np.nanquantile(rb,[.025,.975])
            bounds=f'[{lo:.3f}, {hi:.3f}]'
        rows.append([name,count,f'{ratio:.3f}' if np.isfinite(ratio) else '계산 불가',bounds])
    return rows


def stage4(s,flag,sections,save):
    rows=[];dist=[];caprows=[];limits=[];account_data={}
    for m in ['kospi','kosdaq']:
        for mode,ex,tag in [('a',None,'포함'),('b',None,'포함'),('c',None,'포함'),('b',flag,'152 제외')]:
            days,r,b,individual,nav,counts=s.account(m,mode,ex)
            account_data[m,mode,tag]=(days,r,b,individual,nav,counts)
            for period in ['2024','2025','2026','all']:
                mask=period_mask(s.d[days],period)
                e=(r[mask]-b[mask])*100
                rows.append([m,LABEL[mode],tag,period,int(mask.sum()),cell(estimate(e)),cell(estimate(counts['cash_series'][mask]))])
            offset_ex=((individual-b[None,:]).mean(axis=1)*100)
            totals=(nav[:,-1]-1)*100
            dist.append([m,LABEL[mode],tag,' / '.join(f'{a:+.4f}' for a in [min(offset_ex),np.median(offset_ex),max(offset_ex)]),' / '.join(f'{a:+.2f}' for a in [min(totals),np.median(totals),max(totals)])])
            limits.append([m,LABEL[mode],tag,counts['trades'],counts['unfilled'],counts['exit_missing'],counts['exit_zero_volume'],counts['exit_locked']])
            for unit in [1,20]:
                for p in ['all','2024','2025','2026']:
                    mask=period_mask(s.d[days],p)
                    for sign,n,ratio,bounds in capture(r[mask],b[mask],unit):
                        caprows.append([m,LABEL[mode],tag,p,'하루' if unit==1 else '20일 비겹침',sign,n,ratio,bounds])
    sections.extend(['## 4. 계좌: 20일 교체·20개 시작 위치',
        f'매 신호일 상위10을 정하되 **각 계좌는 20거래일마다** 다음 날 시가 진입, t+20 종가 청산. 시작 위치 0~19의 20계좌를 각각 초기자금 1로 시작한다. 공통 달력 {s.d[s.start+1]}~{s.d[s.stop+19]}; 예정 첫 진입 전과 마지막 청산 후에는 현금. 원 신호 기간만 사용하고 마지막 보유분의 20일 경로까지 평가한다. 계좌 연도는 일수익 날짜 기준으로 2절의 신호 연도와 다르다.',
        '각 자리 예산 10%에는 매수비용 0.25%를 포함해 실제 주식 투입액=0.1/1.0025, 매도 때 당시 주식 평가액의 0.25%를 차감한다. 미체결은 예산 전체 현금(이자 0, 비용 0). 보유 주식 수는 고정하므로 수익에 따라 종목·현금 비중이 변한다. 첫날은 시가→종가, 이후 종가→종가. 매일 동일가중으로 되돌리지 않는다. 잔존 현금은 추가 매수하지 않는다.',
        '아래는 20계좌의 NAV를 합친 계좌(같은 초기자금, 이후 비중 자연 변화)의 일수익과 해당 시장 지수 종가→종가 일수익 차이. 첫날 매수 전 밤사이 지수 수익도 지수에는 포함된다. CI는 **날짜 20일 이동블록**이며 20개 시작 위치를 표본으로 재추출하지 않는다.',
        table(['시장','선정','급변 표지','기간','n 거래일','지수 대비 하루 차이 %p 95%','종가 후 현금 % 95%'],rows),
        '현금 비중은 종가 후 평가 기준으로, 매 20일 청산 직후 전액 현금과 시작·종료 경계의 대기를 포함한다. 미체결 자리만의 비율은 1절과 다르다.',
        '**시작 위치 분포는 기술통계**. 같은 시세를 겹쳐 써 독립 표본이 아니다. 별도 CI를 만들지 않았다.',
        table(['시장','선정','급변 표지','위치별 하루 차이 최소/중앙/최대 %p','위치별 전체 누적수익 최소/중앙/최대 %'],dist),
        '하루 따라간 비율=지수 상승/하락일의 계좌 평균수익÷그날들 지수 평균수익. 20일은 e5_overlay.stats와 같이 달력 앞에서부터 비겹침 복리 수익을 묶어 같은 비율을 계산(끝의 20일 미만은 제외). 연도 표는 해당 연도 처음부터 다시 묶는다. 하락 비율 <1이면 덜 하락, 음수면 해당 하락 표본에서 계좌가 평균 상승했다는 뜻. 각 부호 n<3이면 구간 계산 불가. 하루 CI는 20일 날짜블록, 20일 표는 비겹침 20일 창 재추출 2,000회. 시작 위치 무작위 분포와 별개다.',
        table(['시장','선정','급변 표지','기간','단위','지수 부호','n','따라간 비율','95%'],caprows),
        '일봉 ffill로 보유 중 결측은 직전 종가 평가, 청산도 마지막 종가로 가정한다. 아래 미거래/잠김 청산은 실제로 그 종가에 팔 수 있었다는 확인이 아니므로 계좌 숫자의 한계다(플래그 중복 가능). 배당·세금 별도 반영 없음, 슬리피지는 고정 비용 외 미반영.',
        table(['시장','선정','급변 표지','체결 자리','미체결 자리','청산일 종가결측','청산일 거래량0','청산일 잠김'],limits)])
    save('1~4 완료. 5~6 미완료.')
    print('STAGE 4 SAVED',flush=True)
    return account_data


def account_check(s,account_data):
    """Independent terminal-value check, using no daily path accumulation."""
    errors=[]
    flag=s.share_flags()
    for (m,mode,tag),(_,r,b,individual,nav,counts) in account_data.items():
        exclude=flag if tag=='152 제외' else None
        for offset in range(20):
            terminals=[]
            for t in range(s.start+offset,s.stop,20):
                js=s.choose(t,m,mode,exclude)
                f=s.filled[t,js]
                gross=s.ff[t+20,js[f]]/s.o[t+1,js[f]]
                terminals.append(((~f).sum()+gross.sum()*.9975/1.0025)/10)
            target=np.prod(terminals)
            errors.append(abs(target-nav[offset,-1]))
    assert max(errors)<1e-10
    return len(errors),max(errors)


def stage5(s,datasets,sections,save):
    rows=[];ties=[];summary={}
    for m in ['kospi','kosdaq']:
        for mode in ['a','b','c']:
            guard();rets,exs,nt,nb,bs=s.tie_draws(m,mode)
            ties.append([m,LABEL[mode],len(s.ts),nt,nb,f'{np.median(bs):.0f}',max(bs)])
            det=datasets[m,mode][0]
            for p in PERIODS:
                mask=period_mask(s.d[s.ts],p)
                rm=rets[:,mask].mean(axis=1);em=exs[:,mask].mean(axis=1)
                summary[m,mode,p]=(np.quantile(em,[.025,.5,.975]),estimate(exs[:,mask].mean(axis=0)))
                deterministic=det.ex.to_numpy()[mask].mean()
                rows.append([m,LABEL[mode],p,int(mask.sum()),' / '.join(f'{a:+.3f}' for a in np.quantile(rm,[.025,.5,.975])),
                             ' / '.join(f'{a:+.3f}' for a in np.quantile(em,[.025,.5,.975])),f'{deterministic:+.3f}',f'{100*(em<=deterministic).mean():.1f}',cell(estimate(exs[:,mask].mean(axis=0)))])
    sections.extend(['## 5. 동점 안 무작위 200회',
        '기본 순서는 재무 5분위 평균 내림차순→20일 평균 거래대금 로그 내림차순→종목코드 오름차순. 점수가 다른 종목의 순서를 바꾸지 않고, 10위 경계에 걸친 **동일 재무점수 그룹**에서 부족한 자리만 비복원 무작위 추출한다. 경계보다 점수가 높은 종목은 반드시 포함. 매일 독립 추첨하는 전체 경로 200회, seed=20261009(코스닥 +1). ⓑ·ⓒ에서는 추출 뒤 미체결 0 처리, 대조도 해당 규약 그대로. 매일 같은 종목 우선순위를 고정하는 다른 무작위 방식은 계산하지 않았다.',
        table(['시장','선정','n 날짜','경계 동점 날짜','선택이 바뀔 수 있는 날짜','경계 동점수 중앙','최대'],ties),
        '아래 2.5/50/97.5%는 **같은 고정 시세에서 동점 추첨만 바꾼 200개 평균의 분포**이며 날짜 표본의 95% CI가 아니다. 기본 백분위는 기본 시총차이 이하인 추첨의 비율. 마지막 열만 무작위 200회 평균 일별 차이에 적용한 날짜 20일 블록 CI이며, 추첨 오차까지 합친 구간은 아니다.',
        table(['시장','선정','기간','n 날짜','추첨 수익% 2.5/중앙/97.5','추첨 시총차이%p 2.5/중앙/97.5','기본 차이 %p','기본 백분위 %','추첨평균 시총차이: 날짜 CI'],rows)])
    save('1~5 완료. 6 미완료.')
    print('STAGE 5 SAVED',flush=True)
    return summary


def composition_ci(s,picks,predicate):
    return estimate(np.array([np.mean(predicate(t,js))*100 for t,js in zip(s.ts,picks)]))


def stage6(s,datasets,sections,save):
    sectors=json.loads((ROOT/'sector_cache.json').read_text(encoding='utf-8'))
    labels=np.array([sectors.get(k,'미분류') for k in s.tick])
    finance=np.array([('금융' in k or '지주' in k or k=='보험') for k in labels])
    names={}
    corp=ROOT/'dart_cache/corp_code.csv'
    if corp.exists():
        a=pd.read_csv(corp,dtype=str);names=dict(zip(a.stock_code,a.corp_name))
    sectorrows=[];sizerows=[];finance_rows=[];toprows=[];excluded={};unknown_rows=[]
    for m in ['kospi','kosdaq']:
        b_picks=datasets[m,'b'][1]
        frequency=np.bincount(np.concatenate(b_picks),minlength=s.N)
        top=np.lexsort((s.tick,-frequency))[:3]
        excluded_mask=np.zeros(s.N,bool);excluded_mask[top]=True
        for j in top:
            contribution=sum(s.ret[t,j]/10 for t,js in zip(s.ts,b_picks) if j in js)/len(s.ts)
            toprows.append([m,s.tick[j],names.get(s.tick[j],''),labels[j],int(frequency[j]),f'{100*frequency[j]/(10*len(s.ts)):.3f}',f'{contribution:+.3f}'])
        for mode in ['a','b','c']:
            picks=datasets[m,mode][1]
            alljs=np.concatenate(picks)
            for sector in sorted(set(labels[alljs]),key=lambda sec:-np.sum(labels[alljs]==sec)):
                n=int(np.sum(labels[alljs]==sector))
                sectorrows.append([m,LABEL[mode],sector,n,cell(composition_ci(s,picks,lambda t,js:labels[js]==sector))])
            for q in range(1,6):
                n=sum(int((s.size[t,js]==q).sum()) for t,js in zip(s.ts,picks))
                sizerows.append([m,LABEL[mode],q,n,cell(composition_ci(s,picks,lambda t,js:s.size[t,js]==q))])
            n=int(finance[alljs].sum())
            finance_rows.append([m,LABEL[mode],len(alljs),n,cell(composition_ci(s,picks,lambda t,js:finance[js]))])
            n_unknown=int((labels[alljs]=='미분류').sum())
            unknown_rows.append([m,LABEL[mode],n_unknown,cell(composition_ci(s,picks,lambda t,js:labels[js]=='미분류'))])
            excluded[m,mode]=s.daily(m,mode,excluded_mask)
    sections.extend(['## 6. 업종·시총 집중과 상위3 제외',
        '업종은 sector_cache.json의 현재 보관 분류로 구성 설명에만 사용한다. 과거 당시 업종을 복원한 자료가 아니다. 금융 문자열을 포함한 분류·보험·지주 문자열을 포함한 분류는 **금융 또는 지주**로 한 번만 센다. 특히 지주·전문서비스라는 묶음은 순수 지주와 전문서비스를 나눌 수 없어서 지주 비중을 정확히 식별하지 못한다. 이 묶음 전체를 포함한 근사 비중이다. 업종·시총 비중은 예정 10자리 기준(미체결도 포함), 전체 644신호일의 구성이다. [ ]는 날짜블록 CI. 업종이 없거나 미분류이면 임의 추정하지 않았다.',
        table(['시장','선정','예정 자리','금융 또는 지주 자리','구성 % 95%'],finance_rows),
        table(['시장','선정','업종 미분류 자리','미분류 % 95%'],unknown_rows),
        table(['시장','선정','시총 분위 (1작음~5큼)','자리','구성 % 95%'],sizerows),
        table(['시장','선정','현재 업종','자리','구성 % 95%'],sectorrows),
        '상위3은 각 시장 **ⓑ의 2024~26 전체 선택 빈도** 내림차순, 동률은 코드순으로 한 번 정했다. 아래 수익 기여는 각 종목의 비용 후 자리 수익 합÷(10×644), 따라서 일별 상위10 평균 수익에 더해지는 %p다. 빈도·기여는 기술통계이며 사후 순위다. 다른 연도·방식에도 같은 3종목을 제외하고 후보·대조 양쪽 재선정한다. 제거 후 7개만 유지하는 방식과 다르다.',
        table(['시장','코드','이름','현재 업종','선택 횟수','자리 비중 %','수익 기여 %p'],toprows),
        table(['시장','선정','감도','기간','n 날짜','예정 자리','미체결','대조 후보-날짜 행','상위3 제외 순수익 % 95%','시총 대조 차이 %p 95%'],result_rows(excluded,prefix='빈도 상위3 제외'))])
    save('1~6 완료. 결론·검증 정리 중.')
    print('STAGE 6 SAVED',flush=True)
    return excluded


def main():
    started=guard()
    inputs=[ROOT/'research/fullscan_20260903/panel.npz',ROOT/'sector_cache.json']+[P/name for name in ['annual_availability.csv','build_info.json','summary.csv','daily_results.csv','predictions_kospi.parquet','predictions_kosdaq.parquet','outcomes.parquet','feature_quintiles.parquet','absolute_values.parquet']]
    def input_hashes():
        return {str(f.relative_to(ROOT)):hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in inputs}
    hashes=input_hashes()
    previous=OUT.read_text(encoding='utf-8')
    marker='\n## 이전 기록\n'
    if marker in previous:
        previous=previous.split(marker,1)[1]
    sections=['# REPLY — 코스피 재무 상위10: 후보 선정과 체결 분리',
              f'시작 {started}. 실측 계산만 표시. 기존 코드·DB·docs 수정, 수집기·배치·DART·KIS 실행 없음. 산출물은 이 답 파일과 계산 코드 두 개.']
    def save(status):
        guard()
        OUT.write_text('\n\n'.join(sections)+f'\n\n## 진행 상태\n\n{status}\n'+marker+'\n'+previous,encoding='utf-8')
    s=Reconstruction()
    passed,base=s.baseline()
    sections+=base
    save('기존 ⓐ 재현 통과. 1~6 계산 전.' if passed else '기존 ⓐ 재현 불일치. 다른 계산은 수행하지 않음. 위 검증표에서 차이 원인 확인 필요.')
    if not passed:
        raise SystemExit('BASELINE FAILED: stopped before corrected calculations')
    print('BASELINE PASS',flush=True)
    if '--baseline-only' in sys.argv:
        return
    datasets=stage1(s,sections,save)
    stage2(s,datasets,sections,save)
    flag,without_flags=stage3(s,sections,save)
    accounts=stage4(s,flag,sections,save)
    account_checks,account_error=account_check(s,accounts)
    tie_summary=stage5(s,datasets,sections,save)
    without_top3=stage6(s,datasets,sections,save)
    b=datasets['kospi','b'][0]
    c=datasets['kospi','c'][0]
    findings=[]
    for mode,data in [('ⓑ',b),('ⓒ',c)]:
        annual=[estimate(data.loc[period_mask(data.date,p),'ex']) for p in ['2024','2025','2026']]
        total=estimate(data.ex)
        findings.append(f'{mode} 시총 대조 차이는 2024 {cell(annual[0])}, 2025 {cell(annual[1])}, 2026 {cell(annual[2])}%p, 전체 {cell(total)}%p다.')
    flagged=estimate(without_flags['kospi','b'][0].ex)
    top3=estimate(without_top3['kospi','b'][0].ex)
    random_all=tie_summary['kospi','b','all'][0]
    random_2026=tie_summary['kospi','b','2026'][0]
    days,ar,ab,*_=accounts['kospi','b','포함']
    account_diff=estimate((ar-ab)*100)
    assert hashes==input_hashes(), 'Input data changed during research'
    sections.extend(['## 결론',
        '흠을 뺀 재계산의 실측: '+' '.join(findings)+f' 따라서 **기본 동점 규칙에서는 세 연도 평균이 같은 양의 방향이고 전체 구간은 0을 걸치지 않지만, 2026년 개별 구간은 0을 걸친다.** ⓑ의 급변152 제외 {cell(flagged)}%p, 빈도 상위3 제외 {cell(top3)}%p도 전체 평균은 남는다(n=644). 다만 동점 추첨의 전체 차이 중앙 {random_all[1]:+.3f}%p(추첨 2.5~97.5%: {random_all[0]:+.3f}~{random_all[2]:+.3f})로 낮아지고 2026 중앙은 {random_2026[1]:+.3f}%p로 음수이며, 계좌의 지수 대비 하루 차이는 {cell(account_diff)}%p(n={len(days)})로 0을 걸친다. 그러므로 재무 규칙만의 독립된 효과나 계좌 우위로 확대할 근거는 부족하다. 일봉 체결 근사·과거 시총·보관 재무 공시 버전의 한계가 남고, 2024~2026은 이미 여러 번 본 자료여서 새로운 독립 증거가 아니다. 여러 감도를 비교한 보정 전 구간이며 **앞으로 쌓이는 자료로만 확인할 수 있다.** 등록·채택 제안은 하지 않는다.',
        '## 검증·재현·질문',
        '- 기존 ⓐ를 먼저 재현하고 통과 뒤에만 1~6을 순서대로 실행했다. 연도별 표·완료 표마다 같은 REPLY에 저장했다. 원 인계 기록은 아래 이전 기록에 보존했다.\n- 새 코드에는 제한시간 시작/각 단계/저장 가드가 있다. 계산 중 큰 파일·별도 CSV·DB를 만들지 않았다. numpy/pandas 메모리 계산이며 운영 코드 import도 없다. 기존 연구 중간 파일은 삭제하지 않았다.\n- 접수일 다음 거래일 가용·550일 만료를 원 코드와 동일하게 구현했다. 최초 공시 원본이 아니라 보관된 연간 보고서 이벤트라는 한계는 해소하지 않았다. 신호일 유니버스·시총도 기존 패널에 포함된 종목과 근사 주식 수에 의존하며 상장폐지·시장 이동을 완전 복원했다고 볼 수 없다.\n- 진행을 막는 미확정 질문은 없다. 지주·전문서비스를 분리하는 과거 자료가 없어 금융 또는 지주 비중은 위 근사 정의로만 설명했다.',
        f'- 계좌 종가 경로와 별개로 각 코호트 종료수익을 직접 곱해 **{account_checks}개 계좌 종료 NAV**를 검산: 최대 절대차 {account_error:.3g}(초기 NAV=1). 모든 날짜·추첨에 대해 동일 재무점수 그룹에서 가능한 최소/최대 수익 범위도 통과했다. 읽은 원자료 {len(inputs)}개 해시는 계산 전후 일치했다.',
        '재현 명령(기존 요약과 운영 자료는 덮어쓰지 않음):\n```powershell\npython research/handoff/code_20261009_kospi_fundamental_clean.py --baseline-only\npython research/handoff/code_20261009_kospi_fundamental_clean.py\n```\n첫 명령은 REPLY에 재현 표까지만 저장한다. 최종 보고서를 유지하려면 두 번째 명령으로 전체 실행한다.\n\n새 산출물: 이 REPLY와 code_20261009_kospi_fundamental_clean.py 두 파일뿐. 작업 기록·운영 파일 갱신은 산출물 두 파일 제한에 따라 하지 않았다. 큰 새 중간 파일 없음.'])
    save('1~6 완료. 못 한 계산 없음. 실제 시가 주문·과거 업종·정확한 시총/최초 공시 버전 복원은 요청 계산의 자료 한계로 남음.')
    print('DONE',OUT,flush=True)


if __name__=='__main__':
    main()
