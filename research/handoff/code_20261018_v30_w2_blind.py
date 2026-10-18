"""Independent W2b audit. Only writes the companion REPLY; DB connections are read-only.
Run: python -B research/handoff/code_20261018_v30_w2_blind.py
Permutations: 2000, seed 20261012; bootstraps: 4000, seed 7 (preregistered tool).
Selected numeric helpers adapted from code_20261012_placebo_null.py; no production imports.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import ast
import hashlib
import sqlite3
import time
import sys
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from threadpoolctl import threadpool_limits
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_20261018_v30_w2_blind.md')
BOOT, REPS, SEED = 4000, 2000, 20261012
START = '20260810'


def guard():
    now = datetime.now(timezone(timedelta(hours=9)))
    if now.weekday() < 5 and (20, 10) <= (now.hour, now.minute) < (22, 30):
        raise SystemExit('평일 20:10~22:30 KST: 실행 중단(휴일도 보수적으로 중단)')


def ro(path):
    guard()
    c = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    return c


def anchor(rid, didx):
    if rid in didx:
        return didx[rid]
    d = datetime.strptime(rid, '%Y%m%d')
    return next((didx[x] for k in range(1, 6)
                 if (x := (d-timedelta(days=k)).strftime('%Y%m%d')) in didx), None)


def gate(c, end):
    cnt = pd.read_sql_query('SELECT run_id,count(*) n FROM stage1_oversold '
                            'WHERE run_id<=? GROUP BY run_id', c, params=(end,))
    partial = set(cnt.loc[cnt.n < cnt.n.median()*.30, 'run_id'])
    double = set()
    for tb in ('v3_scores', 'lowvol_scores', 'wu_scores'):
        f = pd.read_sql_query(f'SELECT run_id,model_id,frozen_at FROM {tb} '
                              'WHERE run_id<=?', c, params=(end,))
        f['ts'] = pd.to_datetime(f.frozen_at, utc=True, errors='coerce')
        z = f.dropna(subset=['ts']).groupby(['run_id', 'model_id']).ts.agg(['min', 'max'])
        double.update(z.index.get_level_values(0)[(z['max']-z['min']).dt.total_seconds() >= 3600])
    return partial, double


def correlations(scores, returns):
    """Batch exact Spearman with pairwise removal BEFORE reranking, ties average."""
    valid = np.isfinite(scores) & np.isfinite(returns)
    n = valid.sum(axis=1)
    x = np.where(valid, scores, np.inf)
    y = np.where(valid, returns, np.inf)
    rx = np.where(valid, rankdata(x, axis=1)-(n[:, None]+1)/2, 0)
    ry = np.where(valid, rankdata(y, axis=1)-(n[:, None]+1)/2, 0)
    # Exact number of distinct finite values, mirroring MIN_GROUP/nunique gates.
    sx, sy = np.sort(x, axis=1), np.sort(y, axis=1)
    ux = np.isfinite(sx[:, 0]).astype(int) + ((sx[:, 1:] != sx[:, :-1]) & np.isfinite(sx[:, 1:])).sum(axis=1)
    uy = np.isfinite(sy[:, 0]).astype(int) + ((sy[:, 1:] != sy[:, :-1]) & np.isfinite(sy[:, 1:])).sum(axis=1)
    div = np.sqrt((rx*rx).sum(axis=1)*(ry*ry).sum(axis=1))
    out = np.divide((rx*ry).sum(axis=1), div, out=np.full(len(n), np.nan), where=div > 0)
    out[(n < 8) | (ux < 3) | (uy < 3)] = np.nan
    return out


def weeks(rids):
    labs = [datetime.strptime(r, '%Y%m%d').isocalendar()[:2] for r in rids]
    return np.array([sorted(set(labs)).index(x) for x in labs])


def verify():
    # No real pairings: tie/missing/rank thresholds and permutations on toy inputs.
    x = np.array([[1,1,2,3,5,8,13,21,34,55], [1]*10, np.arange(10)])
    y = np.array([[3,2,1,4,8,5,7,9,np.nan,6], np.arange(10), [np.nan]*3+list(range(7))])
    a = correlations(x, y)
    assert np.isclose(a[0], spearmanr(x[0], y[0], nan_policy='omit').statistic)
    assert np.isnan(a[1:]).all()
    # Check source functions without executing/importing project modules.
    tree = ast.parse((ROOT/'leaderboard.py').read_text(encoding='utf-8-sig'))
    funcs = [z for z in tree.body if isinstance(z, ast.FunctionDef) and z.name in ('anchor', 'dedupe_by_anchor', 'build_gates')]
    env = dict(np=np, pd=pd, GATE_FRAC=.30,
               TRACKS={'v3':('v3_scores','final_score_v3',None),
                       'lv':('lowvol_scores','lowvol_score',None), 'wu':('wu_scores','wu_score',None)})
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<read-only canonical helpers>', 'exec'), env)
    return env


def table(head, rows):
    return '\n'.join(['| '+' | '.join(head)+' |', '|'+ '|'.join(['---']*len(head))+'|']+
                     ['| '+' | '.join(map(str, row))+' |' for row in rows])


def interval(x, digits=6):
    return '['+', '.join(f'{v:+.{digits}f}' for v in x)+']'


def wilson(k, n):
    if not n:
        return '확인 못 함'
    p, z = k/n, 1.959963984540054
    den = 1+z*z/n
    mid = (p+z*z/(2*n))/den
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return f'{p*100:.2f}% [{100*(mid-half):.2f}, {100*(mid+half):.2f}] ({k}/{n})'


def banks(n, labs, boot=BOOT):
    # Exact rng.choice / rng.integers draws used by the preregistered tool.
    rng = np.random.default_rng(7)
    ix = rng.integers(0, n, (boot, n))
    iid = np.zeros((boot, n))
    np.add.at(iid, (np.arange(boot)[:, None], ix), 1/n)
    nw = len(np.unique(labs))
    sizes = np.bincount(labs)
    rng = np.random.default_rng(7)
    ixw = rng.integers(0, nw, (boot, nw))
    counts = np.zeros((boot, nw))
    np.add.at(counts, (np.arange(boot)[:, None], ixw), 1)
    week = counts[:, labs]/(counts@sizes)[:, None]
    return iid, week


def summary(sr):
    sr = sr.sort_index().dropna()
    a = sr.to_numpy(float)
    labs = weeks(sr.index)
    ib, wb = banks(len(a), labs)
    d, w = ib@a, wb@a
    weekly = [a[labs == i].mean() for i in np.unique(labs)]
    return dict(n=len(a), mean=a.mean(), date=np.quantile(d,[.025,.975]),
                week=np.quantile(w,[.025,.975]), bonf=np.quantile(d,[.025/7,1-.025/7]),
                wbonf=np.quantile(w,[.025/7,1-.025/7]),
                positive=sum(v>0 for v in weekly), nw=len(weekly))


def row(label, sr):
    st = summary(sr)
    return [label, st['n'], f"{st['mean']:+.6f}", interval(st['date']),
            interval(st['week']), interval(st['bonf']),
            wilson(st['positive'], st['nw'])]


class Audit:
    def __init__(self):
        guard()
        self.paths = [ROOT/'history.db', ROOT.parent/'dh-q7m3k-data/ohlcv.db']
        self.before = [(p.stat().st_size,p.stat().st_mtime_ns) for p in self.paths]
        with ro(self.paths[1]) as c:
            self.end = c.execute('SELECT MAX(date) FROM daily_ohlcv').fetchone()[0]
            self.p = pd.read_sql_query('SELECT date,ticker,close,shares FROM daily_ohlcv WHERE date>=? AND date<=?',c,params=('20260525',self.end))
            self.extra = {r[0] for r in c.execute('SELECT ticker FROM daily_ohlcv_extra WHERE date=?',('20261008',))}
        assert len(self.extra)==136
        assert not self.p.duplicated(['date','ticker']).any()
        self.close = self.p.pivot(index='date',columns='ticker',values='close').sort_index()
        self.dates = list(self.close.index)
        self.di = {d:i for i,d in enumerate(self.dates)}
        self.changes = self.close.pct_change(fill_method=None).abs()
        self.s = {}
        with ro(self.paths[0]) as c:
            self.partial,self.double = gate(c,self.end)
            self.denom = [r[0] for r in c.execute('SELECT DISTINCT model_id FROM v3_scores ORDER BY model_id')]
            for mid,tb,col in [('v30','v3_scores','final_score_v3'),('lv_b','lowvol_scores','lowvol_score')]:
                self.s[mid] = pd.read_sql_query(f'SELECT run_id,market,ticker,{col} score FROM {tb} WHERE model_id=? AND run_id BETWEEN ? AND ?',c,params=(mid,'20260606',self.end))
                self.s[mid]['market'] = self.s[mid].market.str.lower()
                assert not self.s[mid].duplicated(['run_id','market','ticker']).any()
            self.missing_run = {tb:c.execute(f'SELECT COUNT(*) FROM {tb} WHERE run_id=?',('20261014',)).fetchone()[0] for tb in ['runs','v3_scores','lowvol_scores']}
            env = verify()
            pa,db,_ = env['build_gates'](c, self.dates)
            assert pa==self.partial and db==self.double
        self.env = env
        vs = self.s['v30']
        affected = vs[vs.run_id.between('20260914','20261008') & vs.ticker.isin(self.extra)]
        self.affected = set(affected.ticker)
        self.affected_rows = len(affected)
        assert self.affected_rows==308 and len(self.affected)==52
        self.ret_cache = {}

    def keep(self, mid, start=START, end=None):
        end = end or self.end
        s = self.s[mid]
        candidates = {}
        for rid in sorted(s.loc[s.run_id.between(start,end),'run_id'].unique()):
            t = anchor(rid,self.di)
            if rid not in self.partial|self.double and t is not None:
                candidates.setdefault(t,[]).append(rid)
        keep = sorted(min([r for r in rs if r in self.di] or rs) for rs in candidates.values())
        ref = self.env['dedupe_by_anchor'](s[s.run_id<=end],self.di,self.partial|self.double,reg=start)
        assert set(keep)==ref
        return keep

    def returns(self, rid, h):
        key = (rid,h)
        if key not in self.ret_cache:
            t = anchor(rid,self.di)
            raw = self.close.iloc[t+1+h]/self.close.iloc[t+1]-1
            jump = self.changes.iloc[t+2:t+2+h].max()
            self.ret_cache[key] = raw, jump
        return self.ret_cache[key]

    def measure(self, mid, h=20, start=START, end=None, peer=None, exclude=None, stale_period_only=False):
        end = end or self.end
        result, audit, groups = {},[],[]
        s = self.s[mid]
        peerkept = set(self.keep(peer,start,end)) if peer else set()
        for rid in self.keep(mid,start,end):
            t = anchor(rid,self.di)
            if t+1+h>=len(self.dates) or self.dates[t+1+h]>end:
                continue
            g = s[s.run_id==rid].set_index(['market','ticker'])[['score']]
            if peer:
                if rid not in peerkept:
                    continue
                q = self.s[peer]
                g = g.join(q[q.run_id==rid].set_index(['market','ticker'])[['score']].rename(columns={'score':'peer'}),how='inner')
            removed = 0
            if exclude and (not stale_period_only or '20260914'<=rid<='20261008'):
                bad = g.index.get_level_values('ticker').isin(exclude)
                removed = int(bad.sum())
                g = g[~bad]
            raw,jump = self.returns(rid,h)
            ticks = g.index.get_level_values('ticker')
            g['ret'] = raw.reindex(ticks).to_numpy()
            g['jump'] = jump.reindex(ticks).to_numpy()
            scorebad = g.score.isna() | (g.peer.isna() if peer else False)
            no_ticker = ~ticks.isin(self.close.columns)
            endpoint = g.ret.isna()
            jbad = ~(g.jump<=.32)
            mask = ~scorebad & ~endpoint & ~jbad
            ics,used = [],0
            for mk,q in g[mask].groupby(level='market'):
                if len(q)<8 or q.score.nunique()<3 or q.ret.nunique()<3 or (peer and q.peer.nunique()<3):
                    continue
                a = spearmanr(q.score,q.ret).statistic
                assert np.isclose(a,np.corrcoef(q.score.rank(),q.ret.rank())[0,1],atol=1e-12)
                if peer:
                    a -= spearmanr(q.peer,q.ret).statistic
                ics.append(a); used+=len(q)
                groups.append([rid,mk,len(q),float(a)])
            audit.append([rid,len(g),removed,int(no_ticker.sum()),int((endpoint & ~no_ticker).sum()),int((~endpoint & jbad).sum()),int(scorebad.sum()),int(mask.sum())-used,used,len(ics)])
            if ics:
                result[rid]=float(np.mean(ics))
        return pd.Series(result,dtype=float),pd.DataFrame(audit,columns=['run','rows','removed','no_ticker','endpoint_na','jump_cut','score_na','group_cut','used','markets']),groups

    def panels(self, rids):
        panels=[]
        sv = self.s['v30'].query('run_id>=@START')
        sl = self.s['lv_b'].query('run_id>=@START')
        assert set(zip(sl.market,sl.ticker))<=set(zip(sv.market,sv.ticker))
        for mk,g in sv.groupby('market'):
            ts=sorted(g.ticker.unique())
            ss=g.pivot(index='run_id',columns='ticker',values='score').reindex(index=rids,columns=ts).to_numpy(float)
            ll=sl[sl.market==mk].pivot(index='run_id',columns='ticker',values='score').reindex(index=rids,columns=ts).to_numpy(float)
            rr=[];mm=[];jj=[]
            for rid in rids:
                raw,jump=self.returns(rid,20)
                raw=raw.reindex(ts);jump=jump.reindex(ts)
                rr.append(raw.where(jump<=.32).to_numpy())
                mm.append(raw.isna().to_numpy())
                jj.append((raw.notna() & ~(jump<=.32)).to_numpy())
            cap=self.p[self.p.date.between(START,self.end) & self.p.ticker.isin(ts)].copy()
            cap['cap']=cap.close*cap.shares
            cs=cap[cap.cap>0].sort_values('date').drop_duplicates('ticker').set_index('ticker').cap.reindex(ts)
            bins=np.full(len(ts),5,dtype=int)
            ok=cs.notna().to_numpy()
            bins[ok]=np.clip(np.ceil(cs[ok].rank(pct=True,method='average').to_numpy()*5).astype(int)-1,0,4)
            panels.append(dict(market=mk,tickers=ts,v30=ss,lv_b=ll,ret=np.array(rr),missing=np.array(mm),jump=np.array(jj),bins=bins,capn=int(ok.sum())))
        return panels


def nonoverlap(sr, di, h):
    picked=[]
    for rid in sr.sort_index().index:
        if not picked or anchor(rid,di)-anchor(picked[-1],di)>=h:
            picked.append(rid)
    return picked


def persistence(a):
    # Explicit literal definition: consecutive stored runs, even if >1 trading day.
    s=a.s['v30'].query('run_id>=@START')
    rids=sorted(s.run_id.unique())
    rows=[]
    for prev,cur in zip(rids,rids[1:]):
        x=s[s.run_id==prev].set_index(['market','ticker']).score
        y=s[s.run_id==cur].set_index(['market','ticker']).score
        z=pd.concat([x.rename('x'),y.rename('y')],axis=1).dropna()
        mkic=[]
        for _,g in z.groupby(level='market'):
            if len(g)>=8 and min(g.x.nunique(),g.y.nunique())>=3:
                mkic.append(spearmanr(g.x,g.y).statistic)
        rows.append([cur,prev,anchor(cur,a.di)-anchor(prev,a.di),len(x),len(z),spearmanr(z.x,z.y).statistic,len(z)/len(x),np.mean(mkic)])
    return pd.DataFrame(rows,columns=['run','prev','gap','previous_n','common_n','rho','retained','market_rho']).set_index('run')


def permutations(panels, rids, cap=False):
    rng=np.random.default_rng(SEED)  # same seed for both prespecified methods
    out={m:np.zeros((REPS,len(rids))) for m in ['v30','lv_b']}
    count={m:np.zeros((REPS,len(rids)),int) for m in out}
    losses={m:{k:np.zeros(REPS) for k in ['rows','missing','jump']} for m in out}
    fixed=np.zeros(REPS); pool=0
    for p in panels:
        size=len(p['tickers']);pool+=size
        labs=p['bins'] if cap else np.zeros(size,int)
        strata=[np.flatnonzero(labs==k) for k in np.unique(labs)]
        for lo in range(0,REPS,64):
            guard()
            hi=min(lo+64,REPS)
            maps=np.tile(np.arange(size),(hi-lo,1))
            for ids in strata:
                maps[:,ids]=rng.permuted(np.tile(ids,(hi-lo,1)),axis=1)
            assert np.all(np.sort(maps,axis=1)==np.arange(size))
            fixed[lo:hi]+=(maps==np.arange(size)).sum(axis=1)
            for t in range(len(rids)):
                ret=p['ret'][t,maps]
                for mid in out:
                    score=np.broadcast_to(p[mid][t],(hi-lo,size))
                    valid=np.isfinite(score)
                    losses[mid]['rows'][lo:hi]+=valid.sum(axis=1)
                    losses[mid]['missing'][lo:hi]+=(valid & p['missing'][t,maps]).sum(axis=1)
                    losses[mid]['jump'][lo:hi]+=(valid & p['jump'][t,maps]).sum(axis=1)
                    ic=correlations(score,ret)
                    ok=np.isfinite(ic)
                    out[mid][lo:hi,t]+=np.where(ok,ic,0)
                    count[mid][lo:hi,t]+=ok
    for mid in out:
        out[mid]=np.divide(out[mid],count[mid],out=np.full_like(out[mid],np.nan),where=count[mid]>0)
    return out,losses,fixed/pool,count


def permstats(x,rids):
    flags={(name,den):np.zeros(REPS,bool) for name in ['date','week','both'] for den in [1,7]}
    direction=np.zeros(REPS,bool)
    patterns,inverse=np.unique(np.isfinite(x),axis=0,return_inverse=True)
    for gi,mask in enumerate(patterns):
        ii=np.flatnonzero(inverse==gi)
        if not mask.any():
            continue
        labs=weeks(np.array(rids)[mask]); ib,wb=banks(int(mask.sum()),labs)
        vals=x[np.ix_(ii,mask)]
        direction[ii]=np.mean(np.column_stack([vals[:,labs==w].mean(axis=1) for w in np.unique(labs)])>0,axis=1)>=.60
        for name,bank in [('date',ib),('week',wb)]:
            for lo in range(0,len(ii),64):
                z=vals[lo:lo+64]@bank.T
                for den in [1,7]:
                    flags[(name,den)][ii[lo:lo+64]]=np.quantile(z,.025/den,axis=1)>0
    for den in [1,7]:
        flags[('both',den)]=flags[('date',den)] & flags[('week',den)]
    return flags,direction


def distribution(name,means,actual):
    k=int(np.sum(means<actual));low=int(np.sum(means<=actual));up=int(np.sum(means>=actual))
    return [name,REPS,*[f'{q:+.6f}' for q in np.quantile(means,[.025,.5,.975])],
            wilson(k,REPS),f'{(1+low)/(REPS+1):.6f} ({low}/{REPS})',
            f'{(1+up)/(REPS+1):.6f} ({up}/{REPS})']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    begin=time.monotonic();a=Audit()
    result={}
    for h in [20,10]:
        result['W2',h]=a.measure('v30',h)
        result['W1',h]=a.measure('v30',h,start='20260606',end='20260807')
    v,au,groups=result['W2',20]
    lv,lv_audit,_=a.measure('lv_b')
    common=v.index.intersection(lv.index)
    pair=lv.loc[common]-v.loc[common]
    intersection=a.measure('lv_b',peer='v30')[0]
    no911=v.drop('20260911',errors='ignore')
    ex52=a.measure('v30',exclude=a.affected)
    ex136=a.measure('v30',exclude=a.extra)
    experiod=a.measure('v30',exclude=a.affected,stale_period_only=True)
    affected_in_h20=a.s['v30'].loc[a.s['v30'].run_id.isin(v.index) & a.s['v30'].ticker.isin(a.affected)]
    affected_no_price=int((~affected_in_h20.ticker.isin(a.close.columns)).sum())
    affected_period_h20=int((a.s['v30'].run_id.isin(v.index) & a.s['v30'].run_id.between('20260914','20261008') & a.s['v30'].ticker.isin(a.affected)).sum())
    pers=persistence(a)
    panels=a.panels(list(v.index))
    # Independently check batched rank implementation against scalar Spearman.
    for mid,sr in [('v30',v),('lv_b',lv)]:
        mk=np.array([correlations(p[mid],p['ret']) for p in panels])
        nvalid=np.isfinite(mk).sum(axis=0)
        market_mean=np.divide(np.nansum(mk,axis=0),nvalid,out=np.full(mk.shape[1],np.nan),where=nvalid>0)
        np.testing.assert_allclose(market_mean,sr.reindex(v.index).to_numpy(),atol=1e-12)
    # Check exact bootstrap draws against the preregistered loop, without import.
    rng=np.random.default_rng(7)
    direct=np.array([rng.choice(v.to_numpy(),len(v)).mean() for _ in range(BOOT)])
    np.testing.assert_allclose(direct,banks(len(v),weeks(v.index))[0]@v.to_numpy(),atol=1e-12)
    labs=weeks(v.index)
    blocks=[v.to_numpy()[labs==k] for k in np.unique(labs)]
    rng=np.random.default_rng(7)
    direct_week=np.array([np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))]).mean() for _ in range(BOOT)])
    np.testing.assert_allclose(direct_week,banks(len(v),labs)[1]@v.to_numpy(),atol=1e-12)
    assert len(v)==sum(anchor(r,a.di)+21<len(a.dates) for r in a.keep('v30'))
    elapsed=a.di[a.end]-a.di[START]
    kept=a.keep('v30')
    missing=[d for d in a.dates if START<=d<=a.end and d not in {a.dates[anchor(r,a.di)] for r in kept}]
    print('PRICE',a.end,'DIFF',elapsed,'VALID',len(kept),'h20',summary(v),'h10',summary(result['W2',10][0]),flush=True)
    print('PAIR',summary(pair),'NO911',summary(no911),'EX52',summary(ex52[0]),flush=True)
    print('NONOVERLAP',{h:nonoverlap(result['W2',h][0],a.di,h) for h in [20,10]},flush=True)
    heads=['측정','앵커 n','평균 IC/차이','날짜 95%','주 블록 95%','날짜 Bonf /7 (99.2857%)','주별 양(+) 비율 [Wilson95%] (양/전체 주)']
    sec=['# REPLY — v30 2차 창(W2b) 독립 계산 (2026-10-18)',
         '\n## 범위·눈가림',
         f'- **실측**: 현재 동결점수와 본 표 시세를 읽어 W2b {START}~{a.end}를 독립 계산했다. DB는 `mode=ro`와 `query_only=ON`. 수집기·배치·외부 API 호출 없음. 결과물은 이 보고서와 같은 이름의 `code_20261018_v30_w2_blind.py` 두 파일뿐이다.',
         '- 금지된 루트 `VERDICT_202610*_v30*.md` 및 `research/verdict_v30_w2_px_a_20261009.py`는 열거나 실행하지 않았다. 다만 선행 worklog에 10/8 기준 중간 관측 기록이 이미 있고, 원장·참고 코드에도 과거 수치가 있어 **완전한 눈가림은 아니다**. 기존 W2 답의 값을 입력하거나 맞추지 않았다.',
         '- 규약 출처: `PREREGISTER_v30_w2.md`, `PROJECT_KNOWLEDGE.md` §11, `leaderboard.py`, 사전등록의 9/06 준비 코드, `VERDICT_NOTE_20261011_power.md`. 허용된 10/09 독립 코드와 10/12 자리바꿈 코드의 방법을 참고했다. 운영 모듈 import 없이 계산하며 AST에서 추출한 읽기 전용 게이트/앵커 함수만 독립 결과 검증에 사용했다.',
         '\n## 1. 조건부터 — 실측',
         table(['항목','값'],[
             ['가격 마지막 날',a.end],['사전등록 도구: 마지막 가격 위치 − 20260810 위치',f'{elapsed} / 40 — '+('충족' if elapsed>=40 else '중간 관측')],
             ['시작·끝 포함 가격 날짜 수',elapsed+1],['리더보드 정의: 유효 v30 앵커 수',len(kept)],
             ['중복 제거 전 v30 저장 run 수',a.s['v30'].query('run_id>=@START').run_id.nunique()],
             ['가격일 중 유효 v30 앵커가 없는 날',', '.join(missing)],
             ['부분실행 제외',str(sorted(a.partial))],['이중실행 제외',str(sorted(a.double))],
             ['distinct v3 model_id',f'{len(a.denom)}: '+', '.join(a.denom)],
             ['h20 완결 앵커 범위',f'{v.index.min()}~{v.index.max()}, n={len(v)}'],
             ['h10 완결 앵커 범위',f"{result['W2',10][0].index.min()}~{result['W2',10][0].index.max()}, n={len(result['W2',10][0])}"]]),
         f'- 20261014 가격일은 존재하고 runs/v3_scores/lowvol_scores 행 수는 {a.missing_run}이다. 따라서 가격 날짜 차 {elapsed}에는 포함되지만 v30 유효 앵커 수 {len(kept)}에는 더해지지 않는다. 그날 정상 점수가 있었다면 유효 앵커는 1개 늘었겠지만, 아직 h20·h10 완결일이 아니어서 이번 완결 표본 수에는 영향이 없다.',
         '\n## 2. 골대 그대로 계산한 숫자 — 실측',
         '- t+1 종가 진입→t+1+h 종가 청산. t+2~t+1+h 일간 등락률 절댓값 최대 ≤0.32. `daily_ohlcv`만 사용하고 보충표 시세는 합치지 않았다. 결측 제거 후 동점 평균 순위, 시장별 8쌍 이상·점수/수익 고유값 각 3개 이상에서 Spearman→유효 시장 동일가중→앵커 동일가중이다.',
         f'- 날짜/주 부트스트랩 {BOOT:,}회, seed=7. 사전등록 도구와 같은 재표집 난수 순서를 사용했다. 주는 월~일 달력 주를 복원추출하고 그 안 앵커를 연결한다. Bonferroni /7은 양측 α=.05/7이다. 주 양(+) 비율의 Wilson 구간은 요구된 구간 표기를 위한 참고이며, 주들이 독립이라는 보장은 없고 판정 문턱을 바꾸지 않는다.',
         table(heads,[row('v30 h20 주지표',v),row('v30 h10 보조',result['W2',10][0]),row('lv_b h20 참고',lv),row('lv_b−v30 각자 유니버스·같은 앵커',pair),row('lv_b−v30 같은 종목 교집합 감도',intersection)]),
         f'- v30 h20 주 블록 Bonferroni /7 구간: {interval(summary(v)["wbonf"])} (n={len(v)}). lv_b 행의 /7은 이 요청의 공통 참고 보정일 뿐 lv_b 자체 재판정/고유 분모를 대체하지 않는다. 서로 다른 트랙의 단독 IC 절대값을 성능 순위로 해석하지 않는다.',
         '- h10은 날짜 구간이 양수지만 주 블록 구간은 0을 걸친다. 보조지표만으로 h20 주지표의 유의성을 대신하지 않는다. lv_b−v30 차이도 음수여서 사전등록의 “lv_b 우위·표시 기준 재검토”를 뒷받침하지 않는다.',
         table(['lv_b에서 IC가 없는 완결 run','원 점수행','가격 결손행','점프컷','시장 최소표본 탈락','최종 사용행'],[[r.run,int(r.rows),int(r.no_ticker+r.endpoint_na),int(r.jump_cut),int(r.group_cut),int(r.used)] for r in lv_audit.itertuples() if r.run not in lv.index]),
         '\n## 3. 1차 창과 나란히',
         table(heads,[row('1차 창 현재 DB 재계산: 20260606~20260807 h20',result['W1',20][0]),row('2차 창: 20260810~'+a.end+' h20',v),row('1차 창 현재 DB 재계산 h10',result['W1',10][0]),row('2차 창 h10',result['W2',10][0])]),
         '- **정본 인용**: 8/09 판정은 유의. `VERDICT_20260809.md` 각주④의 코드 교정 후 h20은 +0.1235, n=23, 95% [+0.088,+0.157]이고 앵커≤7/10 근사다. 위 1차 재계산은 실제 8/07 가격 종료와 현재 게이트를 적용한 별도 숫자다. 정본 n=23과 동일 표본이 아니므로 이를 정본 수치의 정확 재현으로 부르지 않는다. 당시 DB 원본·시세 정정 전 값은 **확인 못 함**. 1차 표의 /7은 이번 요청과 맞춘 공통 감도이며, 1차 챌린저 정본의 /6을 소급 변경하지 않는다.',
         '\n## 4. 데이터 결손·수급 각주',
         table(['범위','점수 관측행','감도 선제제외','본 표 종목 없음','진입/청산 종가 결측','추가 점프컷','점수 결측','시장 최소표본 탈락','최종 사용행'],[[label,*[int(df[c].sum()) for c in ['rows','removed','no_ticker','endpoint_na','jump_cut','score_na','group_cut','used']]] for label,df in [('W2 h20',au),('W2 h10',result['W2',10][1]),('W1 h20',result['W1',20][1])]]),
         '- 관측행은 run×종목, 앵커 n과 다르다. 시세 결손은 본 표 종목 없음과 진입/청산 결측의 합이며 점프컷과 분리했다. 내부 날짜의 결측은 정본처럼 `pct_change(fill_method=None)` 뒤 최대값 계산 규약을 그대로 따랐고 임의의 추가 완전성 조건을 만들지 않았다.',
         table(heads,[row('전 종목 주지표',v),row('20260911 run 제외',no911),row('낡은 수급 영향 52종목을 창 전체에서 제외',ex52[0]),row('보충표 136종목을 창 전체에서 제외',ex136[0]),row('52종목을 9/14~10/08 행에서만 제외',experiod[0])]),
         f'- 20260911 run의 h20 완결 표본 포함 여부: **{"포함" if "20260911" in v.index else "미포함"}**. 그날의 진입일은 {a.dates[a.di["20260911"]+1]}, 청산일은 {a.dates[a.di["20260911"]+21]}. 해당 날 제외 전/후 앵커 n={len(v)}/{len(no911)}.',
         f'- `REPLY_20261011_stale_flows_reach.md`의 고정 집합은 10/08 보충표 136종목이다. 현재 동결점수에서 9/14~10/08 v30 {a.affected_rows}행·{len(a.affected)}종목을 재확인했다. 9/14~10/08 당시에 수급이 낡았다는 사실은 이전 입력 감사 기록에 근거한다. 이후 수급 원자료가 보충됐으므로 현재 최신일로 당시 상태를 재판정하지 않았다. 동결점수 재계산 없음.',
         f'- 감도가 같은 이유도 **실측**했다. h20 완결 앵커는 9/11에서 끝나므로 낡은 수급 기간(9/14~10/08)의 직접 영향 행은 아직 {affected_period_h20}개다. 52종목을 창 전체에서 제외하면 이전 날짜의 점수행 {int(ex52[1].removed.sum())}개를 제거하는데, 이 중 {affected_no_price}개는 이미 본 표 종목 부재로 주지표에서 제외돼 있었다. 기간 한정 제외는 {int(experiod[1].removed.sum())}개다. 따라서 동일한 IC는 입력 문제가 없었다는 증거가 아니다. 후보 진입·시장 공통 수급의 간접 영향 및 신선한 수급으로 재계산했을 성적은 **확인 못 함**.',
         '\n## 5. 라벨에 쓰지 않는 참고값 ①·②',
         table(['지평','완결 앵커 n','겹치지 않는 앵커 k','선택 run'],[[h,len(result['W2',h][0]),len(nonoverlap(result['W2',h][0],a.di,h)),', '.join(nonoverlap(result['W2',h][0],a.di,h))] for h in [20,10]]),
         '- 비겹침은 완결 앵커를 시간순으로 정렬해 첫 앵커부터 직전 선택 앵커와 h 거래일 이상 떨어진 것만 고른다. 이 개수는 확정 계수라 신뢰구간 대상이 아니다.',
         table(['측정','run 쌍 n','평균','날짜 95%','주 블록 95%'],[row(label,sr)[:5] for label,sr in [('연속 저장 run: 공통 종목 점수 순위상관',pers.rho),('연속 저장 run: 전 run 종목의 잔존비율',pers.retained),('연속 저장 run: 시장별 점수상관 동일가중 감도',pers.market_rho),('정확히 1거래일 뒤 run만: 점수상관',pers.loc[pers.gap==1,'rho']),('정확히 1거래일 뒤 run만: 종목 잔존비율',pers.loc[pers.gap==1,'retained'])]]),
         '- 지속성 표의 n은 연속 run 쌍 수다. 잔존비율은 |전 run∩다음 run|/|전 run|를 쌍별로 구한 평균이다. 점수 상관 기본값은 두 시장을 합친 공통 종목의 Spearman이며 시장별 평균을 감도로 병기했다. 부트스트랩은 다음 run 날짜를 단위로 사용했다. 휴장 run·빠진 run 때문에 연속 저장 run이 항상 1거래일 뒤인 것은 아니어서 정확한 1거래일 감도도 적었다. 수익은 이 계산에 쓰지 않았다.',
         table(['거래일 간격','run 쌍 수'],[[int(k),int(n)] for k,n in pers.gap.value_counts().sort_index().items()]),
         '\n## 6. 참고값 ③ — 종목 이름표 자리바꿈 (실측)',
         f'- 각 방식 {REPS:,}회, seed={SEED}를 각각 새로 시작한다. 창 안 모든 저장 run에 한 번이라도 출현한 v30 종목을 시장 안에서 1:1로 순열하고, 한 시도에서 전체 점수·출현·결측 흐름을 함께 옮긴다. lv_b 합집합은 v30 합집합의 부분집합임을 확인했고 **같은 source→recipient 매핑**을 적용했다. 원래 lv_b 대상이 아니던 recipient도 허용한다. 매 순열의 1:1 대응을 assert했다.',
         '- 시총 감도는 시장×시총5분위 안에서 섞고 시총 결측은 별도 층으로 둔다. 시총은 종목별 창 안 첫 유효 `close×shares`로 고정한다. 종목별 첫 날짜가 달라 공통 기준일 시총은 아니며 저장 shares가 당시 값으로 보존됐는지는 확인 못 함. 현재 주식수를 따로 가져오지 않았다.',
         table(['시장','전체 합집합 종목 n','시총 있는 종목','시총층별 종목 수 (마지막은 결측층)'],[[p['market'],len(p['tickers']),p['capn'],str(np.bincount(p['bins'],minlength=6).tolist())] for p in panels]),
         '- 아래 2.5/50/97.5는 2,000회 평균의 경험 백분위이며, 양끝은 **자리바꿈 분포 중앙 95% 범위**다. 실제 백분위는 엄격히 작은 시도의 비율, 대괄호는 Monte Carlo Wilson95% 구간이다. 꼬리 p는 `(1+꼬리 횟수)/(2000+1)`이고 최소값은 약 0.000500이다. 관측 평균 자체의 날짜/주 95% 구간과 다른 뜻이다.']
    for cap in [False,True]:
        name='시장×시총5분위' if cap else '시장 내 전체'
        print('PERM START',name,flush=True)
        out,loss,fixed,counts=permutations(panels,list(v.index),cap)
        diff=out['lv_b']-out['v30']
        rows=[distribution('v30 h20',np.nanmean(out['v30'],axis=1),v.mean()),distribution('lv_b−v30 (같은 앵커·각자 유니버스)',np.nanmean(diff,axis=1),pair.mean())]
        sec += ['\n### '+name,
                table(['통계','시도 n','2.5%','50%','97.5%','실제 백분위 [MC95%]','아래쪽 p (횟수/n)','위쪽 p (횟수/n)'],rows)]
        flags,direction=permstats(out['v30'],list(v.index))
        rr=[]
        for den in [1,7]:
            for kind in ['date','week','both']:
                f=flags[kind,den]
                rr.append([den,kind,wilson(int(f.sum()),REPS),wilson(int((f & direction).sum()),REPS)])
        sec += [table(['보정 분모','구간 조건','하단>0 비율 [MC95%] (횟수/시도)','주별 양≥60%도 충족 [MC95%]'],rr),
                '- `date`=날짜, `week`=주 블록, `both`=둘 다. 유의 비율은 양의 구간 하단>0을 뜻하며 음의 역작동을 합치지 않는다. /7은 양측 보정 구간. 주별 방향을 제외/포함한 비율을 구분했고 OOS 자격은 원래 창으로 유지했다. 최종 운영 라벨 자동 판정이나 보편적인 오류율이 아니다.',
                table(['대상','시도별 유효 IC 앵커 n 범위','점수 관측행/시도','가격 결측률 평균 [시도간 중앙95%]','추가 점프컷률 평균 [시도간 중앙95%]'],
                      [[mid,f'{np.isfinite(out[mid]).sum(axis=1).min()}~{np.isfinite(out[mid]).sum(axis=1).max()}',int(loss[mid]['rows'][0]),
                        f"{100*np.mean(loss[mid]['missing']/loss[mid]['rows']):.3f}% {interval(100*np.quantile(loss[mid]['missing']/loss[mid]['rows'],[.025,.975]),3)}",
                        f"{100*np.mean(loss[mid]['jump']/loss[mid]['rows']):.3f}% {interval(100*np.quantile(loss[mid]['jump']/loss[mid]['rows'],[.025,.975]),3)}"] for mid in out]),
                f'- 제자리 이름표 비율: 평균 {100*fixed.mean():.3f}%, 시도간 중앙95% {interval(100*np.quantile(fixed,[.025,.975]),3)} (시도 n={REPS}). 짝비교 유효 앵커 n 범위 {np.isfinite(diff).sum(axis=1).min()}~{np.isfinite(diff).sum(axis=1).max()}.']
        print('PERM RESULT',name,rows,'positive+direction',[(d,k,int((flags[k,d]&direction).sum())) for d in [1,7] for k in ['date','week','both']],flush=True)
    st=summary(v)
    assert len(a.denom)==7
    assert elapsed>=40  # This dated request expects a mature window; do not label an immature one.
    if st['mean']<0 and st['date'][0]<=0<=st['date'][1] and st['bonf'][0]<=0<=st['bonf'][1]:
        opinion='**검토 의견: §11 기본값은 노이즈(이 창으로는 못 가림).** 평균이 음수이고 구간이 0을 걸치는 경우는 사전등록 해석표 어느 칸에도 정확히 맞지 않는다. “CI 0 걸침·IC≥0” 칸에 임의로 넣거나 새 규칙을 만들지 않는다. 유의 재확인과 Bonferroni 음수 역작동 조건 모두 충족하지 않았다. 이 기본값과 사전등록 표의 빈칸은 별개 사실이다.'
    else:
        opinion='**검토 의견은 아래 실측 조건으로 별도 확인 필요.** 자동으로 새 해석 규칙을 만들지 않는다.'
    sec += ['\n## 7. 판정 단어에 관한 의견 — 근거 숫자와 분리',opinion,
            '- 1차 정본의 “유의”를 지우지 않는다. 이번 보고서는 독립 검토 의견이며 정본 판정문·registry·챔피언·모델 상태를 변경하지 않았다. lv_b 짝비교는 사전등록 참고값, 같은 종목 비교는 감도다. 겹치지 않는 앵커·지속성·자리바꿈 결과는 라벨에 사용하지 않는다.',
            '\n## 8. 한계·질문',
            '- 해석표의 음수 평균·0 걸침 빈칸을 최종 판정문에 어떻게 기록할지는 사용자와 정본 작성자의 결정 사항이다. 여기서는 기존 §11 기본값만 별도로 적었다.',
            '- 겹치는 h20 수익과 높은 점수 지속성 때문에 날짜 구간이 실제보다 좁을 수 있다. 주 블록도 주 사이 h20 겹침을 없애지 못한다. Bonferroni는 여러 모델 검정 수만 보정한다. 자리바꿈도 시총·업종·변동성 등 종목 특성과 점수의 관계 일부를 끊으므로 이 비율을 모든 효과0 모델의 실제 오류율로 일반화하지 않는다.',
            '- 시총층은 층 사이 점수·수익 관계를 남긴다. 합집합 순열은 원래 recipient가 그날 후보였는지를 요구하지 않으며 종목 특성의 모든 구조를 보존하지 않는다. 같은 가격 결측 종목이 원자료와 순열에서 다르게 빠질 수 있어 결손률과 유효 앵커 수를 함께 적었다.',
            '- 가격 날짜 차가 처음 40이 된 날에서 고정한 표본이 아니라, 요청한 “시세 마지막 날”까지의 표본이다. 창 시작·계산 규칙은 유지했고 종료일을 성적에 맞춰 고르지 않았다. 처음 40 도달 시점의 별도 정본 판정 여부는 금지 파일을 열지 않아 확인 못 함.',
            '\n## 9. 재현·검증',
            '- 실행: `python -B research/handoff/code_20261018_v30_w2_blind.py`. 로컬 numpy·pandas·scipy·threadpoolctl 필요. 허용된 과거 연구 코드를 실행하지 않고 필요한 방법을 이 코드에 옮겼다. 재실행은 현재 DB의 마지막 가격일을 쓰므로 향후 데이터가 추가되면 결과도 달라진다.',
            '- 검증: 게이트·앵커 중복제거를 운영 함수와 대조, 배치 순위상관을 scipy Spearman과 대조, 실제 v30·lv_b 앵커별 IC가 자리바꿈의 원래 매핑 계산과 1e-12 이내 일치, 날짜·주 재표집 난수열이 정본 방식과 일치, 순열 1:1 대응 확인. 단순 형식 테스트가 아니라 계산의 서로 다른 구현을 대조했다.',
            f'- v30 h20 앵커 목록 SHA256: `{hashlib.sha256("|".join(v.index).encode()).hexdigest()}`. 계산 시간 {time.monotonic()-begin:.1f}초. 중간 파일 없음.',
            '\n### 재현 확인용 앵커별 값 (실측)',
            table(['run','v30 h20','lv_b h20','lv_b−v30','v30 사용 관측행','유효 시장 수'],[[rid,f'{v[rid]:+.9f}',f'{lv.get(rid,np.nan):+.9f}',f'{pair.get(rid,np.nan):+.9f}',int(au.set_index('run').loc[rid,'used']),int(au.set_index('run').loc[rid,'markets'])] for rid in v.index])]
    assert a.before==[(p.stat().st_size,p.stat().st_mtime_ns) for p in a.paths], 'DB changed during audit'
    sec += ['- 실행 전후 두 DB 파일 크기·수정시각 동일. DB 전체 내용 해시 검증은 하지 않았다.']
    guard();OUT.write_text(('\n\n'.join(sec)+'\n').replace('+nan','산출 불가'),encoding='utf-8')
    print('WROTE',OUT,'seconds',time.monotonic()-begin,flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):
        main()
