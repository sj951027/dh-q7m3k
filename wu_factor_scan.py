# -*- coding: utf-8 -*-
"""wu_factor_scan.py — 전체종목 신규 팩터 스캔 (research 탐색, 2026-07-11)
OHLCV_DB 환경변수 또는 ../dh-q7m3k-data/ohlcv.db 필요. 산출은 콘솔+CSV, 게이트 면제.
⚠️ 전부 in-sample 가설 — 등록 아님. 등록은 wu 판정(9월) 후 PREREGISTER 절차로만.
"""
# -*- coding: utf-8 -*-
"""전체종목 신규 팩터 스캔 (research) — 가설 방향 사전 고정, h20 주지표.
미탐색 축: 모멘텀의 질(FIP)·복권성(MAX)·유동성(Amihud)·매집(OBV)·수급(flows)·신용(credit).
전부 in-sample 가설 생산 — 등록 아님."""
import sqlite3, sys
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OH=__import__('os').environ.get('OHLCV_DB','../dh-q7m3k-data/ohlcv.db')
con=sqlite3.connect(f'file:{OH}?mode=ro',uri=True)
raw=pd.read_sql("SELECT ticker,date,close,volume,shares FROM daily_ohlcv",con)
for c in ('close','volume','shares'): raw[c]=pd.to_numeric(raw[c],errors='coerce')
piv=lambda v: raw.pivot_table(index='ticker',columns='date',values=v,aggfunc='last').sort_index(axis=1)
C=piv('close'); V=piv('volume'); SH=piv('shares')
dates=list(C.columns); R=C.pct_change(axis=1,fill_method=None)
AMT=C*V
print(f"[가격패널] {C.shape[0]}종목×{len(dates)}일")

# 가드 (whole_score 상속)
def guards(i):
    w=R[dates[max(0,i-20):i+1]]
    n=w.notna().sum(axis=1)
    rv=w.std(axis=1,ddof=1)
    ok=(rv>=0.003)&((w==0).sum(axis=1)/n.where(n>0)<=0.5)&(w.abs().max(axis=1)<=0.30)
    amt20=AMT[dates[max(0,i-19):i+1]].mean(axis=1)/1e8
    return ok&(amt20>=5.0)

def fwd(i,h):
    seg=C[dates[i:i+h+1]]
    r=seg.pct_change(axis=1,fill_method=None)
    bad=r.abs().max(axis=1)>0.32
    return ((seg[dates[i+h]]/seg[dates[i]]-1)*100).where(~bad)

# 가설 방향 사전 고정 (True=큰값이 좋다)
DIR={'fip':True,'max5':False,'amihud':True,'obv63':True,'volmom':True,
     'upratio63':True,'amt_trend':True,'nh_fresh':False,
     'nh252':True,'mom12':True,'big':True,'lv63':False}
DESC={'fip':'모멘텀의 질(부드러운 추세, frog-in-pan)','max5':'복권성(21일 최대급등 평균) — 낮을수록',
 'amihud':'비유동성 프리미엄 |r|/거래대금','obv63':'매집(OBV 63일 순증/총거래량)',
 'volmom':'변동성조정 모멘텀 mom12/lv63','upratio63':'상승일 비율(63일)',
 'amt_trend':'거래대금 팽창 amt20/amt63','nh_fresh':'신고가 경과일 — 신선할수록',
 'nh252':'52주고가 근접(기존)','mom12':'12-1모멘텀(기존)','big':'시총(기존)','lv63':'저변동(기존)'}

def factors_at(i):
    F=pd.DataFrame(index=C.index)
    c_now=C[dates[i]]
    w63=R[dates[max(0,i-62):i+1]]
    F['lv63']=w63.std(axis=1,ddof=1).where(w63.notna().sum(axis=1)>=30)
    F['nh252']=c_now/C[dates[max(0,i-251):i+1]].max(axis=1)-1
    mom12=C[dates[i-21]]/C[dates[i-252]]-1
    F['mom12']=mom12
    F['big']=np.log10((c_now*SH[dates[i]]).where(lambda x:x>0))
    # 신팩터
    w231=R[dates[i-252:i-21]]  # mom12와 같은 창
    pos=(w231>0).sum(axis=1); neg=(w231<0).sum(axis=1); tot=w231.notna().sum(axis=1)
    F['fip']=np.sign(mom12)*((pos-neg)/tot.where(tot>=100))
    w21=R[dates[max(0,i-20):i+1]]
    F['max5']=w21.apply(lambda row: row.nlargest(5).mean(),axis=1)
    amt63=AMT[dates[max(0,i-62):i+1]]
    F['amihud']=(w63.abs()/(amt63/1e8)).mean(axis=1)
    obv=(np.sign(R[dates[max(0,i-62):i+1]])*V[dates[max(0,i-62):i+1]])
    F['obv63']=obv.sum(axis=1)/V[dates[max(0,i-62):i+1]].sum(axis=1)
    F['volmom']=mom12/F['lv63']
    F['upratio63']=(w63>0).sum(axis=1)/w63.notna().sum(axis=1)
    F['amt_trend']=AMT[dates[max(0,i-19):i+1]].mean(axis=1)/amt63.mean(axis=1)
    hi252=C[dates[max(0,i-251):i+1]]
    F['nh_fresh']=hi252.apply(lambda row:(len(row)-1-int(np.nanargmax(row.values))) if row.notna().any() else np.nan,axis=1)
    return F

H=20; STEP=20
anchors=list(range(273,len(dates)-H,STEP))
print(f"[앵커] {len(anchors)}개 step={STEP} h={H}")
rows=[]; dec=[]
for i in anchors:
    ok=guards(i); r=fwd(i,H)
    uni=C.index[ok&r.notna()]
    if len(uni)<300: continue
    ru=r.reindex(uni); ex=ru-ru.median()
    F=factors_at(i)
    yr=dates[i][:4]
    for f,d in DIR.items():
        x=F.loc[uni,f]; m=x.notna()
        if m.sum()<200: continue
        ic=x[m].rank().corr(ru[m].rank())
        sic=ic if d else -ic
        rows.append((dates[i],yr,f,sic,int(m.sum())))
        q=x[m].rank(pct=True,ascending=d)
        top=q[q>=0.9].index
        dec.append((dates[i],yr,f,ru.reindex(top).mean(),ex.reindex(top).mean()))
ic=pd.DataFrame(rows,columns=['date','yr','f','sic','n'])
dc=pd.DataFrame(dec,columns=['date','yr','f','abs','exc'])
rng=np.random.default_rng(7)
out=[]
for f,g in ic.groupby('f'):
    v=g['sic'].values
    bs=[rng.choice(v,len(v)).mean() for _ in range(2000)]
    d=dc[dc.f==f]
    yr_ic=g.groupby('yr')['sic'].mean()
    out.append((f,v.mean(),np.percentile(bs,2.5),np.percentile(bs,97.5),len(v),
                d['abs'].mean(),d['exc'].mean(),
                yr_ic.get('2024',np.nan),yr_ic.get('2025',np.nan),yr_ic.get('2026',np.nan)))
res=pd.DataFrame(out,columns=['factor','IC','ci_lo','ci_hi','n','top10_abs%','top10_exc%','IC24','IC25','IC26']).sort_values('IC',ascending=False)
pd.set_option('display.width',150)
print("\n== 단일팩터 h20 signed IC (가설방향 고정) · 상위10% 수익 · 연도 안정성 ==")
print(res.to_string(index=False,float_format=lambda x:f"{x:+.3f}"))
res.to_csv('research/wf_singles.csv',index=False)


# ======================================================================
# 2단계: 조합 대결


H=20; STEP=20
anchors=list(range(273,len(dates)-H,STEP))
COMBOS={
 'wu_a(기존)':      [('lv63',False),('nh252',True),('mom12',True),('big',True)],
 'wu_b(기존)':      [('nh252',True),('mom12',True)],
 'c1_wu_a+max5':    [('lv63',False),('nh252',True),('mom12',True),('big',True),('max5',False)],
 'c2_max5대체lv':   [('max5',False),('nh252',True),('mom12',True),('big',True)],
 'c3_up추가':       [('nh252',True),('mom12',True),('big',True),('upratio63',True)],
 'c4_질모멘텀':     [('nh252',True),('upratio63',True),('max5',False),('big',True)],
}
# 직교성: 팩터 간 rank 상관 (최근 앵커 기준)
Flast=factors_at(anchors[-1]); ok=guards(anchors[-1])
uni0=C.index[ok]
sub=Flast.loc[uni0,['lv63','max5','upratio63','nh252','mom12']].rank()
print("[직교성] 팩터 rank 상관 (최신 앵커):")
print(sub.corr().round(2).to_string())

rows=[]
for i in anchors:
    ok=guards(i); r=fwd(i,H)
    uni=C.index[ok&r.notna()]
    if len(uni)<300: continue
    ru=r.reindex(uni); ex=ru-ru.median()
    F=factors_at(i)
    for name,fac in COMBOS.items():
        s=None; core=None
        for j,(f,d) in enumerate(fac):
            rk=F.loc[uni,f].rank(pct=True,ascending=d)
            if j==0: core=rk.notna(); filled=rk
            else: filled=rk.fillna(0.5)
            s=filled if s is None else s+filled
        s=s.where(core)
        m=s.notna()
        ic=s[m].rank().corr(ru[m].rank())
        top=s[m].nlargest(50).index
        rows.append((dates[i],name,ic,ru.reindex(top).mean(),ex.reindex(top).mean()))
df=pd.DataFrame(rows,columns=['date','combo','ic','top50_abs','top50_exc'])
rng=np.random.default_rng(7)
print("\n== 조합 h20: IC·top50 수익·누적(23앵커 복리, 리밸당 비용 0.5%p 차감) ==")
print(f"{'combo':16} {'IC':>7} {'95%CI':>17} {'top50절대%':>10} {'top50초과%':>10} {'누적%':>8} {'적중%':>6}")
for name,g in df.groupby('combo',sort=False):
    v=g['ic'].values
    bs=[rng.choice(v,len(v)).mean() for _ in range(2000)]
    cum=(np.prod(1+(g['top50_abs'].values-0.5)/100)-1)*100
    hit=(g['top50_abs']>0).mean()*100
    print(f"{name:16} {v.mean():+.3f} [{np.percentile(bs,2.5):+.3f},{np.percentile(bs,97.5):+.3f}]"
          f" {g['top50_abs'].mean():>+10.2f} {g['top50_exc'].mean():>+10.2f} {cum:>+8.1f} {hit:>6.0f}")
ewcum=(np.prod(1+df[df.combo=='wu_a(기존)'].merge(
    pd.DataFrame(),how='left',left_index=True,right_index=True)['top50_abs']*0)-1)  # placeholder
# EW 시장 대조
mkt=[]
for i in anchors:
    ok=guards(i); r=fwd(i,H); uni=C.index[ok&r.notna()]
    if len(uni)>=300: mkt.append(r.reindex(uni).median())
print(f"\n[대조] EW시장 23앵커 평균 {np.mean(mkt):+.2f}%/20d · 누적 {(np.prod(1+np.array(mkt)/100)-1)*100:+.1f}%")
df.to_csv('research/wf_combos.csv',index=False)


# ======================================================================
# 3단계: 연도 분해 + 수급/신용


H=20; STEP=20
anchors=list(range(273,len(dates)-H,STEP))
COMBOS={
 'wu_a(기존)':   [('lv63',False),('nh252',True),('mom12',True),('big',True)],
 'c3_up추가':    [('nh252',True),('mom12',True),('big',True),('upratio63',True)],
 'c3nb(big제외)':[('nh252',True),('mom12',True),('upratio63',True)],
 'up단독+big':   [('upratio63',True),('big',True)],
}
rows=[]
for i in anchors:
    ok=guards(i); r=fwd(i,H); uni=C.index[ok&r.notna()]
    if len(uni)<300: continue
    ru=r.reindex(uni); F=factors_at(i)
    for name,fac in COMBOS.items():
        s=None
        for j,(f,d) in enumerate(fac):
            rk=F.loc[uni,f].rank(pct=True,ascending=d)
            filled=rk if j==0 else rk.fillna(0.5)
            if j==0: core=rk.notna()
            s=filled if s is None else s+filled
        s=s.where(core); m=s.notna()
        top=s[m].nlargest(50).index
        rows.append((dates[i][:4],name,ru.reindex(top).mean()))
df=pd.DataFrame(rows,columns=['yr','combo','top50'])
print("== 연도별 top50 평균 %/20d (비용 전) ==")
print(df.pivot_table(index='combo',columns='yr',values='top50',aggfunc='mean').round(2).to_string())
print("적중(>0 비율):")
print(df.assign(hit=df.top50>0).pivot_table(index='combo',columns='yr',values='hit',aggfunc='mean').round(2).to_string())

# ---- 수급(flows, 50거래일)·신용(short_flows, 125일) 축 ----
fl=pd.read_sql("SELECT ticker,date,foreign_net_val,inst_net_val,pension_net_val FROM daily_flows",con)
for c in fl.columns[2:]: fl[c]=pd.to_numeric(fl[c],errors='coerce')
sf=pd.read_sql("SELECT ticker,date,credit_bal_rate,loan_chg FROM short_flows",con)
for c in ('credit_bal_rate','loan_chg'): sf[c]=pd.to_numeric(sf[c],errors='coerce')
pf=lambda d,v: d.pivot_table(index='ticker',columns='date',values=v,aggfunc='last').sort_index(axis=1)
FN,IN_,PN=pf(fl,'foreign_net_val'),pf(fl,'inst_net_val'),pf(fl,'pension_net_val')
CR=pf(sf,'credit_bal_rate')
def flow_scan(P,name,d_hyp,start,step):
    idxs=[i for i in range(len(dates)-H) if dates[i]>=start and (i-273)%step==0 and dates[i] in P.columns]
    # 앵커: P에 20일 이력 존재
    res=[]
    for i in range(273,len(dates)-H,step):
        dt_=dates[i]
        cols=[c for c in P.columns if c<=dt_][-20:]
        if len(cols)<15: continue
        ok=guards(i); r=fwd(i,H); uni=C.index[ok&r.notna()]
        if len(uni)<300: continue
        mcap=C[dt_]*SH[dt_]
        x=(P[cols].sum(axis=1).reindex(uni))/(mcap.reindex(uni))
        m=x.notna()& (mcap.reindex(uni)>0)
        if m.sum()<200: continue
        ic=x[m].rank().corr(r.reindex(uni)[m].rank())
        res.append(ic if d_hyp else -ic)
    if res:
        print(f"  {name:12} signed IC {np.mean(res):+.3f}  (n_anchor={len(res)}, 개별 {['%+.2f'%v for v in res]})")
    else:
        print(f"  {name:12} 표본 부족")
print("\n== 수급 20일 순매수/시총 (h20, ⚠️ 앵커 극소 — 참고만) ==")
flow_scan(FN,'외국인',True,'20260527',5)
flow_scan(IN_,'기관',True,'20260527',5)
flow_scan(PN,'연기금',True,'20260527',5)
print("== 신용잔고율(과열=나쁨 가설, 125일) ==")
res=[]
for i in range(273,len(dates)-H,10):
    dt_=dates[i]
    if dt_ not in CR.columns: continue
    ok=guards(i); r=fwd(i,H); uni=C.index[ok&r.notna()]
    if len(uni)<300: continue
    x=CR[dt_].reindex(uni); m=x.notna()
    if m.sum()<200: continue
    res.append(-(x[m].rank().corr(r.reindex(uni)[m].rank())))
print(f"  credit_rate  signed IC {np.mean(res):+.3f} (n_anchor={len(res)}, 개별 {['%+.2f'%v for v in res]})" if res else "  표본 부족")
