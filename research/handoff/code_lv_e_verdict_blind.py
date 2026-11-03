"""Independent lv_e audit. Only writes the companion REPLY; DB connections are read-only.
Run: python -B research/handoff/code_lv_e_verdict_blind.py
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
import json
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('REPLY_lv_e_verdict_blind.md')
BOOT, REPS, SEED = 4000, 2000, 20261012
START = '20260901'


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
                week=np.quantile(w,[.025,.975]), bonf=np.quantile(d,[.025/11,1-.025/11]),
                wbonf=np.quantile(w,[.025/11,1-.025/11]),
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
            self.p = pd.read_sql_query('SELECT date,ticker,close,shares,volume FROM daily_ohlcv WHERE date>=? AND date<=?',c,params=('20260525',self.end))
        assert not self.p.duplicated(['date','ticker']).any()
        self.close = self.p.pivot(index='date',columns='ticker',values='close').sort_index()
        self.dates = list(self.close.index); self.di = {d:i for i,d in enumerate(self.dates)}
        self.changes = self.close.pct_change(fill_method=None).abs(); self.s = {}
        with ro(self.paths[0]) as c:
            self.partial,self.double = gate(c,self.end)
            self.denom = [r[0] for r in c.execute('SELECT DISTINCT model_id FROM lowvol_scores ORDER BY model_id')]
            assert len(self.denom)==11, 'Denominator changed: report both denominators before proceeding'
            for mid in ['lv_e','lv_b']:
                self.s[mid] = pd.read_sql_query('SELECT run_id,market,ticker,lowvol_score score,n_universe,spec_hash FROM lowvol_scores WHERE model_id=? AND run_id BETWEEN ? AND ?',c,params=(mid,START,self.end))
                self.s[mid]['market'] = self.s[mid].market.str.lower()
                assert not self.s[mid].duplicated(['run_id','market','ticker']).any()
            self.rawuni = pd.read_sql_query('SELECT run_id,market,ticker,realized_vol,roe_value FROM stage3_final WHERE run_id BETWEEN ? AND ? AND oversold_score>=30 AND oversold_score<70 AND "amt_avg_1m_억">=5',c,params=(START,self.end))
            self.rawuni['market']=self.rawuni.market.str.lower()
            self.rawuni=self.rawuni.groupby(['run_id','market']).filter(lambda g:len(g)>=10)
            self.missing_run = {tb:c.execute('SELECT COUNT(*) FROM '+tb+' WHERE run_id=?',('20261014',)).fetchone()[0] for tb in ['runs','v3_scores','lowvol_scores']}
            self.env=verify();pa,db,_=self.env['build_gates'](c,self.dates)
            assert pa==self.partial and db==self.double
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

    def panels(self, rids, h=20):
        panels=[]
        sv = self.s['lv_e'].query('run_id>=@START')
        sl = self.s['lv_b'].query('run_id>=@START')
        assert set(zip(sl.market,sl.ticker))<=set(zip(sv.market,sv.ticker))
        for mk,g in sv.groupby('market'):
            ts=sorted(g.ticker.unique())
            ss=g.pivot(index='run_id',columns='ticker',values='score').reindex(index=rids,columns=ts).to_numpy(float)
            ll=sl[sl.market==mk].pivot(index='run_id',columns='ticker',values='score').reindex(index=rids,columns=ts).to_numpy(float)
            rr=[];mm=[];jj=[]
            for rid in rids:
                raw,jump=self.returns(rid,h)
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
            panels.append(dict(market=mk,tickers=ts,lv_e=ss,lv_b=ll,ret=np.array(rr),missing=np.array(mm),jump=np.array(jj),bins=bins,capn=int(ok.sum())))
        return panels


def nonoverlap(sr, di, h):
    picked=[]
    for rid in sr.sort_index().index:
        if not picked or anchor(rid,di)-anchor(picked[-1],di)>=h:
            picked.append(rid)
    return picked


def persistence(a):
    # Explicit literal definition: consecutive stored runs, even if >1 trading day.
    s=a.s['lv_e'].query('run_id>=@START')
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
    rng=np.random.default_rng(SEED)  # same seed, pool and batches for both horizons/models
    out={m:np.zeros((REPS,len(rids))) for m in ['lv_e','lv_b']}
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
    flags={(name,den):np.zeros(REPS,bool) for name in ['date','week','both'] for den in [1,11]}
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
                for den in [1,11]:
                    flags[(name,den)][ii[lo:lo+64]]=np.quantile(z,.025/den,axis=1)>0
    for den in [1,11]:
        flags[('both',den)]=flags[('date',den)] & flags[('week',den)]
    return flags,direction


def distribution(name,means,actual):
    k=int(np.sum(means<actual));low=int(np.sum(means<=actual));up=int(np.sum(means>=actual))
    return [name,REPS,*[f'{q:+.6f}' for q in np.quantile(means,[.025,.5,.975])],
            wilson(k,REPS),f'{(1+low)/(REPS+1):.6f} ({low}/{REPS})',
            f'{(1+up)/(REPS+1):.6f} ({up}/{REPS})']



def coverage(a):
    f=a.p.copy(); f['ratio']=f.volume/f.shares.replace(0,np.nan)
    grid=f.pivot_table(index='date',columns='ticker',values='ratio',aggfunc='last').sort_index()
    turn=grid.rolling(20,min_periods=1).mean()
    cov=[];u=a.rawuni.copy();u['to20']=[turn.at[r,t] if r in turn.index and t in turn.columns else np.nan for r,t in zip(u.run_id,u.ticker)]
    for rid,g in u.groupby('run_id'):
        cov.append([rid,len(g),int(g.to20.notna().sum()),float(g.to20.notna().mean())])
    keys=['run_id','market','ticker']
    recalcs=[]
    for _,g in u.groupby(['run_id','market']):
        g=g.copy();g['score_new']=g.realized_vol.rank(pct=True,ascending=False)+g.roe_value.rank(pct=True).fillna(.5)+g.to20.rank(pct=True,ascending=False).fillna(.5)
        recalcs.append(g[keys+['score_new']])
    rec=pd.concat(recalcs).merge(a.s['lv_e'][keys+['score']],on=keys,how='outer',indicator=True)
    both=rec[rec['_merge']=='both'];diff=(both.score_new-both.score).abs()
    bad=both.loc[diff>1e-10].groupby('run_id').size().to_dict()
    outside=rec[rec['_merge']!='both'].merge(u[keys+['realized_vol']],on=keys,how='left')
    return pd.DataFrame(cov,columns=['run','universe','available','coverage']),dict(paired=len(both),outside=int((rec['_merge']!='both').sum()),outside_core_missing=int(outside.realized_vol.isna().sum()),missing=int(diff.isna().sum()),mismatch=int((diff>1e-10).sum()),max_abs=float(diff.max()),mismatch_by_run=bad)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    begin=time.monotonic(); a=Audit(); kept=a.keep('lv_e')
    elapsed=a.di[a.end]-a.di[START]
    missing=[d for d in a.dates if START<=d<=a.end and d not in {a.dates[anchor(r,a.di)] for r in kept}]
    ready=len(kept)>=40 and elapsed>=40
    results={};rows=[];audits=[];anchorrows=[];stats={}
    for h in [20,10]:
        for mid in ['lv_e','lv_b']:
            sr,au,gr=a.measure(mid,h);results[mid,h]=sr;stats[mid,h]=summary(sr)
            rows.append(row(f'{mid} h{h}',sr))
            sums=au.select_dtypes('number').sum()
            audits.append([mid,h,*[int(sums[k]) for k in ['rows','no_ticker','endpoint_na','jump_cut','score_na','group_cut','used']]])
        e,b=results['lv_e',h],results['lv_b',h];ix=e.index.intersection(b.index)
        pair=e.loc[ix]-b.loc[ix];inter=a.measure('lv_e',h,peer='lv_b')[0]
        results['pair',h]=pair;stats['pair',h]=summary(pair)
        rows.extend([row(f'lv_e-lv_b h{h} 각자 유니버스',pair),row(f'lv_e-lv_b h{h} 같은 종목',inter)])
        assert pair.index.equals(inter.index) and np.allclose(pair,inter,atol=1e-12)
        for rid in ix:anchorrows.append([h,rid,f'{e[rid]:+.9f}',f'{b[rid]:+.9f}',f'{pair[rid]:+.9f}'])
    cov,match=coverage(a)
    uni=[]
    for rid in kept:
        x=a.s['lv_e'].query('run_id==@rid');y=a.s['lv_b'].query('run_id==@rid')
        kx=set(zip(x.market,x.ticker));ky=set(zip(y.market,y.ticker))
        uni.append([rid,len(x),len(y),len(kx&ky),len(kx|ky),len(kx&ky)/len(kx|ky)])
        assert kx==ky
    pers=persistence(a)
    pstats={c:summary(pers[c]) for c in ['rho','retained','market_rho']}
    one=pers[pers.gap==1]
    # Independent arithmetic checks: batched ranks and bootstrap random draws.
    for h in [20,10]:
        rids=list(results['lv_e',h].index)
        for mid in ['lv_e','lv_b']:
            mm=np.array([correlations(p[mid],p['ret']) for p in a.panels(rids,h)])
            np.testing.assert_allclose(np.nanmean(mm,axis=0),results[mid,h].to_numpy(),atol=1e-12)
    e=results['lv_e',20];rng=np.random.default_rng(7)
    direct=np.array([rng.choice(e.to_numpy(),len(e)).mean() for _ in range(BOOT)])
    np.testing.assert_allclose(direct,banks(len(e),weeks(e.index))[0]@e.to_numpy(),atol=1e-12)
    print('ELIGIBILITY',a.end,elapsed,len(kept),'MISSING',missing,flush=True)
    print('OBSERVED',[(k,{'n':v['n'],'mean':v['mean'],'date':v['date'].tolist(),'week':v['week'].tolist(),'bonf':v['bonf'].tolist(),'positive':v['positive'],'nw':v['nw']}) for k,v in stats.items()],flush=True)
    sec=['# REPLY — lv_e §11 독립 계산 (2026-11-04)',
         '## 0. 범위·눈가림 한계',
         '- **실측**: 운영 history.db와 ohlcv.db를 URI mode=ro 및 query_only로 읽었다. 수집기·네트워크·운영 코드 실행·docs/DB 쓰기 없음. 산출물은 이 보고서와 동행 코드 두 파일뿐이다. 운영 판정/승격을 적용하지 않았다.',
         '- **완전한 눈가림 아님**: 이전 세션에서 중간 숫자를 보았고, 이번 worklog/README 목록에 Claude의 11/3 중간값과 11/4 판정 초안 라벨·숫자가 노출됐다. lv_e VERDICT 본문과 research/verdict_lv_e_*.py는 독립 계산 완료 전 열거나 실행하지 않았다. 계산 코드는 허용된 10/18 v30 W2b 코드의 수치 보조함수를 재사용·조정하고 lv_e 입력/커버리지/보고를 새로 작성했다. 최신 worklog 본문은 다음 진화 검토의 독립 의견 고정 전까지 보류했다.',
         f'- 입력 마감 {a.end}; 점수 등록 필터 {START}~{a.end}. 재계산된 6/05 이후 등록 전 점수는 제외. lowvol distinct={len(a.denom)}: '+', '.join(a.denom)+'.',
         '- 가격은 leaderboard lowvol 경로와 같은 daily_ohlcv 본표만 사용. 보충표를 더해 판정 표본을 바꾸지 않았다. 시세 없는 종목 손실은 아래에 별도 기록.',
         f'- 코드 SHA256: `{hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}`. DB 시작 size/mtime_ns: `{a.before}`.',
         '## 1. 조건부터',
         f'- 가격 날짜 차 = {a.di[a.end]} − {a.di[START]} = **{elapsed}**; 등록 후 유효 앵커 **{len(kept)}**. '+('40 조건 충족, 판정 의견 가능.' if ready else '**중간 관측**: 판정 의견 없음.'),
         f'- 등록일부터 끝까지 가격일 {elapsed+1}개 중 유효 앵커 없는 날: {missing}. 20261014는 가격 달력에 있으나 run이 없어 가격 날짜 차는 늘고 유효 앵커는 늘지 않는다. 해당일 행수: {a.missing_run}.',
         f'- 독립 게이트: 부분실행 {sorted(a.partial)}, 이중실행 {sorted(a.double)}. 20260608·20260703은 등록 전 창 밖. 운영 함수의 AST 추출본과 독립 산출 집합/중복제거를 assert로 대조했다.',
         '## 2. IC·짝비교',
         '- 추천 다음 거래일 종가 진입, 그 뒤 h거래일 종가 수익. 시장별 최소8쌍·점수/수익 고유값3개. 시장평균→앵커 동일가중. 점프컷은 t+2~t+1+h 일간 절댓값>32%. 날짜/월~일 주 블록 부트스트랩 각4,000회 seed7. 주블록은 감도이며 새 판정 기준을 만들지 않았다. Bonferroni 양측99.545455%(/11).',
         table(['측정','앵커 n','평균 IC/diff','날짜95%','주블록95%','날짜 Bonf /11','양(+) 주 Wilson95% (양/전체)'],rows),
         '- 각자 유니버스 짝비교와 같은 종목 교집합 감도는 수치 허용오차1e-12 내 같다. 두 모델의 등록 후 run별 시장·ticker 집합이 전부 동일하기 때문이다.',
         '### 관측 제외 수(종목×앵커, 중복 종목을 앵커마다 셈)',
         table(['모델','h','입력행','가격열 없음','진입/종료가격 결측','점프컷','점수 결측','시장그룹 조건 미달','IC 사용행'],audits),
         '- 위 결측/점프컷은 순차 분류이며 가격열 없음과 endpoint 결측을 중복 집계하지 않는다. h가 끝나지 않은 앵커는 이 표에 들어가지 않는다.',
         '## 3. 유니버스와 to20',
         f'- 등록 후 두 모델 각 {len(a.s["lv_e"]):,}점수행 / {len(uni)}run. run별 교집합/합집합 비율은 모두100%. spec_hash lv_e={sorted(a.s["lv_e"].spec_hash.unique())}, lv_b={sorted(a.s["lv_b"].spec_hash.unique())}. 아래 표는 재구성한 DEFAULT_UNI 분모와 to20 현행 DB 커버리지다.',
         f'- to20은 volume/shares를 전체 본표 날짜 격자로 만든 뒤 rolling(20,min_periods=1). 기준일 이후 값 미사용. raw stage3에서 과매도30 이상70 미만·평균거래대금5억 이상·시장유니버스10개 이상을 재구성. 등록 후 최소 커버리지 **{100*cov.coverage.min():.4f}%**, 90% 미만 run **{int((cov.coverage<.9).sum())}**.',
         f'- **시점 한계**: lowvol_scores에 원래 to20 원값/결측 마스크는 저장되지 않는다. 이는 현행 자료 재구성 커버리지이지 과거 적재 순간 장애까지 직접 확인한 값은 아니다. 현재 재구성한 realized_vol+ROE+to20 순위합과 동결점수 대조: `{match}`. 저장점수 밖32행은 모두 핵심 realized_vol 결측으로 제외된 행이다. 공통행656개의 점수 차이는 실제 재현 불일치이며, 원자료 정정/적재시점 차이 중 원인은 확인 못 함. 따라서 재구성 점수로 판정 입력을 바꾸지 않고 동결 lowvol_score를 그대로 사용했다. 당시 to20 커버리지까지 입증됐다고 보지 않는다.',
         table(['run','유니버스 n','to20 있음 n','비율'],[[r.run,int(r.universe),int(r.available),f'{r.coverage*100:.4f}%'] for r in cov.itertuples()]),
         '### 두 모델 run별 종목 집합',
         table(['run','lv_e n','lv_b n','교집합 n','합집합 n','교집합/합집합'],[[*r[:5],f'{r[5]*100:.1f}%'] for r in uni]),
         '- 코드 확인: DEFAULT_UNI는 oversold_score·amt_avg_1m_억, lv_e 점수는 realized_vol·roe·to20이다. lv_b도 수급 성분을 쓰지 않는다. lowvol_score가 공매도 자료를 함께 읽는 경로는 있으나 lv_e 선택 팩터/유니버스에는 쓰지 않는다. 따라서 9/14~10/08 낡은 KIS 수급 사고는 이 판정 입력과 무관하다.',
         '- 재무 시점 각주: lowvol ROE는 valuation_daily(EPS/BPS, 공시일 없음) 유래라 공시 시점 확인 못 함. 현행 데이터 재계산 일치와 공시시점 안전성은 다른 확인이다.',
         '## 4. 참고값(라벨에 사용하지 않음)',
         table(['h','완결 앵커 n','겹치지 않는 n','선택 앵커'],[[h,len(results['lv_e',h]),len(nonoverlap(results['lv_e',h],a.di,h)),', '.join(nonoverlap(results['lv_e',h],a.di,h))] for h in [20,10]]),
         '- 점수 지속성: 저장된 연속 run의 공통 종목 순위상관 평균과 이전 run 대비 잔존율. 시장 합친 literal 정의와 시장별 평균을 함께 제공. 수익을 쓰지 않는다. 거래일 간격이1이 아닌 쌍도 별도 표시.',
         table(['측정','run쌍 n','평균','날짜95%','주블록95%'],[[c,s['n'],f'{s["mean"]:.6f}',interval(s['date']),interval(s['week'])] for c,s in pstats.items()]),
         f'- 거래일 간격 분포: `{pers.gap.value_counts().sort_index().to_dict()}`. 정확히1거래일 간격만 rho: '+str(row('gap1 rho',one.rho))+'. retained는 비율이며, 위 구간은 날짜 재표집 참고 구간이다.',
         '### 자리바꿈 2,000회 · seed20261012',
         '- 창 안 한 번이라도 나온 종목의 점수·출현·결측 흐름 전체를 같은 시장 안에서 다른 이름에1:1 대응. 두 모델에 같은 매핑. h20/h10도 같은 종목 풀·같은 매핑을 사용한다. 시총5분위 감도는 창 안 최초 유효 close×shares로 고정, 결측은 별도 집단. 이는 결과를 보고 유리한 분할을 고르지 않기 위한 동일한 기존 W2b 정의다.']
    perm_all={}
    for cap in [False,True]:
        label='시총5분위 내' if cap else '시장 내 전체'
        fstats={};dirs={};means={}
        for h in [20,10]:
            rids=list(results['lv_e',h].index);panels=a.panels(rids,h)
            out,loss,fixed,counts=permutations(panels,rids,cap)
            out['pair']=out['lv_e']-out['lv_b']
            print('PERM',label,h,'pool',[(p['market'],len(p['tickers']),p['capn']) for p in panels],flush=True)
            for mid in ['lv_e','lv_b','pair']:
                fstats[mid,h],dirs[mid,h]=permstats(out[mid],rids)
                means[mid,h]=np.nanmean(out[mid],axis=1)
            sec.append(f'#### {label} h{h}')
            sec.append(table(['측정','반복 n','null2.5%','null50%','null97.5%','실제값 백분위 Wilson95%','하단꼬리 +1 보정(n/2000)','상단꼬리 +1 보정(n/2000)'],[distribution(mid,means[mid,h],stats[mid,h]['mean']) for mid in ['lv_e','lv_b','pair']]))
            sec.append(f'- 고정된 자기 이름 비율 평균 {fixed.mean():.6f}; 풀(시장,n,시총있음) '+str([(p['market'],len(p['tickers']),p['capn']) for p in panels])+'. '+f'lv_e 순열별 평균 제외: 가격결측 {loss["lv_e"]["missing"].mean():.2f}, 점프컷 {loss["lv_e"]["jump"].mean():.2f} 종목×앵커. 유효 시장수 범위 {int(counts["lv_e"].min())}~{int(counts["lv_e"].max())}.')
        base=fstats['lv_e',20]['date',1]&dirs['lv_e',20]
        bonf=base&fstats['lv_e',20]['date',11]
        wb=bonf&fstats['lv_e',20]['week',1]
        full=wb&fstats['lv_e',10]['date',1]&fstats['pair',20]['date',1]&fstats['pair',10]['date',1]
        sec.append(table(['뒤섞음 통과 검사','횟수/2000와 Wilson95%'],[[name,wilson(int(x.sum()),REPS)] for name,x in [('h20 날짜95%+양의 주60%',base),('위 조건+Bonf /11',bonf),('위 조건+주블록95%',wb),('위 조건+h10 날짜95%+짝 h20/h10 날짜95%',full)]]))
        sec.append('- 마지막 줄은 h10 재현을 날짜95% 하단>0으로 두고 짝 두 지평을 모두 요구한 명시적 결합 검사다. 아래처럼 h10 보정/주별/주블록까지 요구한 더 엄격한 수도 병기한다. 참고 시험이며 실제 승격 조건의 빈 문구를 새로 정하지 않는다.')
        strict=full&fstats['lv_e',10]['date',11]&fstats['lv_e',10]['week',1]&dirs['lv_e',10]
        sec.append('h10 보정/주별/주블록까지: '+wilson(int(strict.sum()),REPS))
    se=stats['lv_e',20];s10=stats['lv_e',10];p20=stats['pair',20];p10=stats['pair',10]
    conditions=[('유효앵커40 이상',len(kept)>=40,f'{len(kept)}'),('가격 날짜 차40 이상',elapsed>=40,f'{elapsed}'),('h20 날짜95% 하단>0',se['date'][0]>0,interval(se['date'])),('양의 주>=60%',se['positive']/se['nw']>=.6,wilson(se['positive'],se['nw'])),('Bonf /11 하단>0',se['bonf'][0]>0,interval(se['bonf'])),('h10 재현(날짜95% 하단>0)',s10['date'][0]>0,interval(s10['date'])),('짝 h20 날짜95% 하단>0',p20['date'][0]>0,interval(p20['date'])),('짝 h10 날짜95% 하단>0',p10['date'][0]>0,interval(p10['date'])),('주블록 h20 하단>0(내림 감도)',se['week'][0]>0,interval(se['week'])),('현행 재구성 to20커버리지 모든run>=90%',bool((cov.coverage>=.9).all()),f'min={cov.coverage.min():.6f}; 적재시점 마스크는 미보존')]
    passed=all(x[1] for x in conditions)
    if not ready:opinion='중간 관측 — 판정 의견 없음'
    elif passed:opinion='유의(승격 후보) — 자동 교체/채택 적용 아님'
    elif se['date'][0]>0 or (se['mean']>.03 and se['date'][0]>-.02):opinion='기움 — 채택 조건 미충족'
    elif se['date'][1]<0:opinion='역작동(유의)' if se['bonf'][1]<0 and se['week'][1]<0 else '역작동(유의 아님)'
    else:opinion='노이즈 — 이 창으로 못 가림'
    sec+=['## 5. 조건 해석표와 별도 의견',table(['사전 조건','충족','근거'],[[name,'✔' if ok else '✘',note] for name,ok,note in conditions]),
          '- 사전등록 §2는 앵커 방향60%, 요청서/공통규약은 주별60%라고 적는다. 정본 충돌을 숨기지 않도록 날짜 양 비율도 병기: '+wilson(int((results['lv_e',20]>0).sum()),len(results['lv_e',20]))+'. 두 해석의 충족 여부를 확인하고 임의로 문턱을 바꾸지 않는다.',
          '- 사전등록 §4의 90% 미만과 괄호 속 “NaN 과반”은 같은 조건이 아니다. 명시된90%를 사용했다. 원래 적재시점 결측률은 직접 확인 못 하므로 현재 자료 재구성이라는 제한을 유지한다.',
          f'**계산자 의견: {opinion}.** 동결점수의 통계 조건과 현행 커버리지 재구성에 기초한 의견이며 Claude 초안 대조 전 고정한다. 당시 커버리지 마스크는 확인 못 했다는 제한을 승격 판단에 함께 전달한다. 정식 판정문·원장·registry 변경은 하지 않았다.',
          '- h10은 날짜95% 및 /11 보정 구간 하단이 양수여서 별도 지평 재현 조건을 충족한다고 읽었다. 다만 h10 주블록은 [-0.004637,+0.246475], 짝 h10 주블록도 [-0.010581,+0.055189]로 0을 걸친다. 이를 숨기지 않는다. h10에도 주블록 양수까지 요구한다면 더 보수적인 해석은 기움이지만, 결과를 본 뒤 그 추가 조건을 새 정본으로 만들지는 않았다.',
          '- 겹침/지속성 때문에 날짜95%와 주블록95%가 실제 반복표본의95% 보장을 준다고 말할 수 없다. 자리바꿈 백분위·통과율은 이 창의 특정 null에서 나온 관측이며 시장 일반의 오류율 또는 추가 판정 p값으로 쓰지 않는다. to20 순위 추가의 표본 내 개선과 향후 돈 기준 우위는 별개다.',
          '## 6. 재현·앵커별 숫자',
          '명령: `python -I -B -X utf8 research/handoff/code_lv_e_verdict_blind.py`. 평일20:10~22:30에는 guard가 중단한다. 관측 끝은 실행시 본표 MAX(date)이므로 나중 재실행하면 창이 늘어난다. 이 보고서의 마감일과 동일한 DB 스냅샷이 있어야 같은 숫자를 재현할 수 있다.',
          table(['h','run','lv_e IC','lv_b IC','차이'],anchorrows)]
    after=[(p.stat().st_size,p.stat().st_mtime_ns) for p in a.paths]
    assert after==a.before,'Input DB changed during audit; report not written'
    sec.append(f'- 입력 DB size/mtime_ns 시작·끝 동일. 자체 순위·부트스트랩·게이트·교집합 대조 assert 통과. 실행 {time.monotonic()-begin:.1f}초. 해석 확정 뒤 운영 반영은 별도 사용자 결정이다.')
    guard();OUT.write_text('\n\n'.join(sec)+'\n',encoding='utf-8')
    print('WROTE',OUT,'OPINION',opinion,flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=1):
        main()
