"""Offline research only. See research/target20_20261003/PLAN.md.
Writes only research/target20_20261003 artifacts. No production imports or network.
python research/handoff/code_target20_20261003.py
"""
from pathlib import Path
import sys,json,hashlib,warnings,sqlite3
import numpy as np
import pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore',category=RuntimeWarning)
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/target20_20261003'
PANEL=ROOT/'research/fullscan_20260903/panel.npz'
SEED=20261003

def log(tag,obj):print(tag,json.dumps(obj,ensure_ascii=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)),flush=True)
def rolling(a,n,minp=None,fn='mean'):
    out=getattr(pd.DataFrame(a).rolling(n,min_periods=minp or n),fn)().to_numpy()
    return out[:,0] if np.ndim(a)==1 else out
def returns(a,k):
    out=np.full(a.shape,np.nan,dtype=float);out[k:]=a[k:]/a[:-k]-1;out[~np.isfinite(out)]=np.nan;return out
def lag(a,k=1):
    out=np.full(a.shape,np.nan,dtype=float);out[k:]=a[:-k];return out
def rank(a,mask):return pd.DataFrame(np.where(mask,a,np.nan)).rank(axis=1,pct=True).to_numpy()
def block_idx(n,h,k=2000):
    if n<=h:return None
    starts=np.random.default_rng(SEED).integers(0,n-h+1,(k,int(np.ceil(n/h))))
    return (starts[:,:,None]+np.arange(h)).reshape(k,-1)[:,:n]
def interval(v,h):
    v=np.asarray(v,float);v=v[np.isfinite(v)];idx=block_idx(len(v),h)
    return [None,None] if idx is None else np.quantile(v[idx].mean(axis=1),[.025,.975]).tolist()

class Study:
    def __init__(self):
        z=np.load(PANEL,allow_pickle=True);self.z=z
        self.d=z['dates'].astype(str);self.tick=z['tick'].astype(str);self.c=z['close'].astype(float)
        self.o=z['open'].astype(float);self.h=z['high'].astype(float);self.l=z['low'].astype(float)
        self.v=z['vol'].astype(float);self.T,self.N=self.c.shape
        self.mk=np.char.lower(z['mk'].astype(str));self.di={d:i for i,d in enumerate(self.d)}
        self.r=returns(self.c,1);self.amt=self.c*self.v;self.start=np.searchsorted(self.d,'20240102')
        self.ff=pd.DataFrame(self.c).ffill().to_numpy()
        self.idx=np.array([pd.Series(z[k]).ffill().to_numpy() for k in ('kospi','kosdaq')]).T
        self.mi=np.where(self.mk=='kospi',0,1)
        self.ok=(rolling((np.abs(self.r)<1e-9).astype(float),63,20)<=.5)&(rolling((np.abs(self.r)>.32).astype(float),21,5,'max')<=0)&(rolling(self.r,21,15,'std')>=.003)&(rolling(self.amt,20,10)>=5e8)&(z['susp']==0)&(self.c>=1000)&(rolling(np.isfinite(self.c).astype(float),252,1,'sum')>=120)
        self.feats={};self.rules={};self.masks={};self.picks={};self.rows=[];self.trades=[]
        log('PANEL',dict(shape=self.c.shape,start=self.d[0],end=self.d[-1],sha256=hashlib.file_digest(PANEL.open('rb'),'sha256').hexdigest(),eligible_latest=int(self.ok[-1].sum())))

    def features(self):
        c,r,v,ok=self.c,self.r,self.v,self.ok
        lv5=rolling(r,5,4,'std');lv20=rolling(r,20,15,'std');lv60=rolling(r,60,40,'std')
        ret5=returns(c,5);ret20=returns(c,20);ret60=returns(c,60);ret120=returns(c,120)
        ma5=rolling(c,5);ma20=rolling(c,20);ma60=rolling(c,60)
        nh=c/rolling(c,252,120,'max')-1
        vr=v/rolling(v,20,15); ar=self.amt/rolling(self.amt,20,15)
        clv=(c-self.l)/np.where(self.h>self.l,self.h-self.l,np.nan)
        rs20=ret20-returns(self.idx,20)[:,self.mi];rs60=ret60-returns(self.idx,60)[:,self.mi]
        mr=returns(self.idx,1)[:,self.mi]
        beta=(rolling(r*mr,60,40)-rolling(r,60,40)*rolling(mr,60,40))/(rolling(mr*mr,60,40)-rolling(mr,60,40)**2)
        downside=np.sqrt(rolling(np.minimum(r,0)**2,60,40))
        upr=rolling((r>0).astype(float),60,40)
        self.feats=dict(rs20=rs20,rs60=rs60,ret5=ret5,ret20=ret20,ret60=ret60,ret120=ret120,nh252=nh,lv20=lv20,lv60=lv60,volume_ratio=vr,amount_ratio=ar,clv=clv,beta=beta,downside=downside,up_fraction=upr,ma20gap=c/ma20-1,contraction=lv5/lv60,acceleration=rs20-rs60/3,log_amount=np.log(rolling(self.amt,20,15)))
        R={k:rank(a,ok) for k,a in self.feats.items()};self.R=R
        def add(name,score,condition=None):
            self.rules[name]=score;self.masks[name]=ok if condition is None else ok&condition
        add('control_amount',R['log_amount']);add('control_highvol',R['lv60'])
        turn=v/self.z['shares'];add('control_price4',(1-R['lv60'])+(1-rank(rolling(turn,20,10),ok))+(1-R['lv20'])+R['nh252'])
        add('relative_high',R['rs60']+R['nh252'])
        breakout=c>lag(rolling(c,20,20,'max'))
        add('breakout20_volume',R['amount_ratio']+R['rs20'],breakout)
        add('contraction_breakout',R['rs60']+R['nh252'],breakout&(lag(lv5/lv60)<.7))
        add('trend_pullback',R['rs60']-R['ret5'],(ma20>ma60)&(c>ma60)&(ret5<0)&(c>self.o))
        add('strong_volume_day',R['rs20']+R['clv'],(r>=.03)&(r<=.15)&(vr>=2)&(clv>=.75))
        add('smooth_momentum',R['rs60']+R['up_fraction'],ret60>0)
        add('risk_adjusted_mom',rank(ret60/np.maximum(lv60,.001),ok),ret60>0)
        add('defensive_high',(1-R['downside'])+R['nh252'])
        add('highbeta_high',R['beta']+R['nh252'])
        add('acceleration_volume',R['acceleration']+R['amount_ratio'])
        add('oversold_reclaim',1-R['ret20'],(ret20<=-.15)&(c>self.o)&(c>ma5)&(lag(c)<=lag(ma5)))
        gap=self.o/lag(c)-1
        add('gap_continuation',R['rs60']+R['volume_ratio'],(gap>=.02)&(gap<=.10)&(c>self.o)&(vr>=1.5))
        log('RULES',list(self.rules))

    def choose(self):
        for name,score in self.rules.items():
            masks=self.masks[name];allp=[]
            for t in range(self.T):
                ix=np.where(masks[t]&np.isfinite(score[t]))[0]
                order=np.argsort(-score[t,ix],kind='stable');allp.append(ix[order[:10]])
            self.picks[name]=allp

    def paths(self,t,h=60,close_entry=False):
        shift=1 if close_entry else 0
        n=min(h,self.T-t-1-shift)
        base=self.c[t+1] if close_entry else self.o[t+1]
        locked=(np.abs(self.h[t+1]-self.l[t+1])<1e-8)&(np.abs(base/self.c[t]-1)>=.295)
        filled=np.isfinite(base)&(base>0)&(self.v[t+1]>0)&~locked
        val=self.ff[t+1+shift:t+n+1+shift]/np.where(filled,base,np.nan)-1
        return val,filled

    def evaluate(self,close_entry=False,only=None,suffix='',cooldown=0,liq=0):
        rows=[];trades=[];selected={}
        for name,picks in self.picks.items():
            if only is not None and name not in only:continue
            chosen=[];last=np.full(self.N,-10000)
            for t,ix in enumerate(picks):
                sel=ix
                if liq:sel=sel[self.feats['log_amount'][t,sel]>=np.log(liq)]
                if cooldown:sel=sel[t-last[sel]>=cooldown]
                last[sel]=t;chosen.append(sel)
            selected[name+suffix]=chosen
        if only is None and not suffix:selected={'universe':[np.where(self.ok[t])[0] for t in range(self.T)],**selected}
        for t in range(self.start,self.T-5):
            path,filled=self.paths(t,60,close_entry=close_entry)
            # Benchmark is net of the same 0.5% only where a trade is feasible.
            benchmarks={}
            for h in (5,10,20,40,60):
                if h>len(path):continue
                raw=path[h-1];net=np.where(filled,raw-.005,0)
                benchmarks[h]=[np.mean(net[self.ok[t]&(self.mi==m)]) for m in (0,1)]
            for name,picks in selected.items():
                ix=picks[t];nf=int(filled[ix].sum());denom=len(ix) if name=='universe' else 10
                if denom==0:continue
                for h,bm in benchmarks.items():
                    p=path[:h,ix];f=filled[ix];net=np.where(f,p[-1]-.005,0)
                    ret=float(np.nansum(net)/denom);bench=float(np.sum(np.asarray(bm)[self.mi[ix]])/denom)
                    # No trade -> no cost and no index exposure for strategy; benchmark retains planned slots.
                    index=(self.idx[t+h+int(close_entry)]/self.idx[t+int(close_entry)]-1)[self.mi[ix]]
                    idxret=float(np.sum(index)/denom)
                    valid=p[:,f];netvalid=valid-.005
                    if nf:
                        peak=np.maximum.accumulate(np.vstack([np.ones((1,nf)),1+valid]),axis=0)[1:]
                        mdd=np.min((1+valid)/peak-1,axis=0)
                        mae=np.min(valid,axis=0)
                        frac=(valid>0).mean(axis=0)
                        hit=(netvalid[-1]>=.20)
                        touch=(np.max(netvalid[4:],axis=0)>=.20) if h>=5 else hit
                        joint=hit&(mae>=-.10)&(frac>=.8)&(valid[0]>0)
                        first=(valid[0]>0)
                    else:
                        mdd=mae=frac=hit=touch=joint=first=np.array([])
                    row=dict(rule=name,date=self.d[t],h=h,n_selected=len(ix),n_filled=nf,ret=ret*100,bench=bench*100,excess=(ret-bench)*100,index=idxret*100,
                      hit_rate=float(np.mean(hit)) if nf else np.nan,touch_rate=float(np.mean(touch)) if nf else np.nan,joint_rate=float(np.mean(joint)) if nf else np.nan,
                      first_up=float(np.mean(first)) if nf else np.nan,mean_mae=float(np.mean(mae)*100) if nf else np.nan,mean_mdd=float(np.mean(mdd)*100) if nf else np.nan,
                      positive_fraction=float(np.mean(frac)) if nf else np.nan,loss_rate=float(np.mean(netvalid[-1]<0)) if nf else np.nan,
                      worst10=float(np.quantile(netvalid[-1],.1)*100) if nf else np.nan,positive_terminal=float(np.mean(netvalid[-1]>0)) if nf else np.nan)
                    rows.append(row)
                    if h==20 and name!='universe':
                        for j,k in enumerate(ix):
                            pp=p[:,j]
                            if not filled[k]:continue
                            peak=np.maximum.accumulate(np.r_[1,pp+1])[1:]
                            trades.append(dict(rule=name,date=self.d[t],ticker=self.tick[k],market=self.mk[k],ret=(pp[-1]-.005)*100,
                              excess=(pp[-1]-.005-bm[self.mi[k]])*100,hit=bool(pp[-1]-.005>=.2),touch=bool(np.max(pp[4:]-.005)>=.2),
                              first_up=bool(pp[0]>0),mae=float(pp.min()*100),mdd=float(np.min((pp+1)/peak-1)*100),positive_fraction=float((pp>0).mean()),
                              joint=bool(pp[-1]-.005>=.2 and pp.min()>=-.1 and (pp>0).mean()>=.8 and pp[0]>0),
                              exit_missing=bool(not np.isfinite(self.c[t+20+int(close_entry),k])),exit_volume_zero=bool(self.v[t+20+int(close_entry),k]<=0),gap=float((self.o[t+1,k]/self.c[t,k]-1)*100)))
            if (t-self.start)%150==0:log('PROGRESS',dict(date=self.d[t],suffix=suffix))
        df=pd.DataFrame(rows);td=pd.DataFrame(trades)
        return df,td

def summarize(df,name='summary.csv'):
    rows=[]
    for (rule,h),g in df.groupby(['rule','h']):
        for year in ('2024','2025','2026','2025-26','all'):
            sub=g if year=='all' else g[g.date>='20250101'] if year=='2025-26' else g[g.date.str.startswith(year)]
            if len(sub)==0:continue
            row=dict(rule=rule,h=h,period=year,n_dates=len(sub),n_active=int((sub.n_filled>0).sum()),n_picks=int(sub.n_filled.sum()),coverage=float((sub.n_filled>0).mean()),avg_slots=float(sub.n_filled.mean()),
                     ret=float(sub.ret.mean()),excess=float(sub.excess.mean()),index_excess=float((sub.ret-sub['index']).mean()))
            for col in ('hit_rate','touch_rate','joint_rate','first_up','mean_mae','mean_mdd','positive_fraction','loss_rate','worst10','positive_terminal'):
                row[col]=float(np.average(sub.loc[sub[col].notna(),col],weights=sub.loc[sub[col].notna(),'n_filled'])) if sub[col].notna().any() else np.nan
            for col in ('ret','excess'):
                bounds=interval(sub[col],h);row[col+'_lo'],row[col+'_hi']=bounds
            for state,m in [('down',sub['index']<0),('up',sub['index']>0)]:
                row[state+'_n']=int(m.sum());row[state+'_ret']=float(sub.loc[m,'ret'].mean());row[state+'_excess']=float(sub.loc[m,'excess'].mean());row[state+'_index_excess']=float((sub.ret-sub['index'])[m].mean())
            rows.append(row)
    result=pd.DataFrame(rows);result.to_csv(OUT/name,index=False,encoding='utf-8-sig');return result

def main():
    OUT.mkdir(exist_ok=True)
    s=Study();s.features();s.choose()
    df,td=s.evaluate();df.to_csv(OUT/'daily_results.csv',index=False,encoding='utf-8-sig');td.to_parquet(OUT/'trades20.parquet',index=False)
    summary=summarize(df)
    out=summary[(summary.h==20)&(summary.period=='2025-26')].sort_values('joint_rate',ascending=False)
    log('H20_OOS',out[['rule','n_dates','n_picks','avg_slots','ret','excess','excess_lo','excess_hi','hit_rate','touch_rate','joint_rate','first_up','mean_mae','mean_mdd','down_index_excess','up_index_excess']].to_dict('records'))
    # Persist feature arrays only for this standalone research continuation, no production state.
    np.savez_compressed(OUT/'research_cache.npz',**{k:a.astype(np.float32) for k,a in s.feats.items()},ok=s.ok)
    latest=[]
    names={}
    corp=ROOT/'dart_cache/corp_code.csv'
    if corp.exists():
        cc=pd.read_csv(corp,dtype=str);names=dict(zip(cc.stock_code,cc.corp_name))
    for rule,p in s.picks.items():
        for n,j in enumerate(p[-1],1):latest.append(dict(asof=s.d[-1],rule=rule,rank=n,ticker=s.tick[j],name=names.get(s.tick[j],''),market=s.mk[j],close=s.c[-1,j],research_score=s.rules[rule][-1,j]))
    pd.DataFrame(latest).to_csv(OUT/'latest_research_candidates.csv',index=False,encoding='utf-8-sig')
    log('SAVED',str(OUT))

if __name__=='__main__':main()
