"""Render existing research results; no DB access or numerical rerun."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/'research/target20_conditions_20261004'
d=pd.read_csv(P/'detailed_moving_blocks.csv')
d=d[d.period.astype(str)=='all']
labels=['ALL','rsi14__abs(-inf,20]','rsi14__abs(20,30]','rsi14__abs(30,50]','rsi14__abs(50,70]','rsi14__abs(70,80]','rsi14__abs(80,inf]']
fig,axs=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
for market,color,offset in [('kospi','#2867aa',-.13),('kosdaq','#dc7932',.13)]:
    t=d[(d.market==market)&d.b.isna()].set_index('a').loc[labels]
    y=[i+offset for i in range(len(labels))]
    for ax,metric,title in zip(axs,['first','hit','ret'],['Entry-day gain rate (%)','Net +20% at day 20 (%)','Mean 20-day net return (%)']):
        ax.hlines(y,t[metric+'_lo'],t[metric+'_hi'],color=color,alpha=.65)
        ax.scatter(t[metric],y,color=color,label=market.upper(),s=22)
        ax.set_title(title);ax.grid(axis='x',alpha=.2);ax.invert_yaxis()
        ax.set_yticks(range(7),['All eligible','RSI <= 20','20 < RSI <= 30','30 < RSI <= 50','50 < RSI <= 70','70 < RSI <= 80','RSI > 80'])
axs[0].axvline(50,color='gray',ls=':',lw=1)
axs[2].axvline(0,color='gray',ls=':',lw=1)
axs[0].legend(loc='lower left')
fig.suptitle('RSI14 by market | 2024-01-02 to 2026-08-25 signals\nPoints: stock-date means; lines: exploratory 95% moving-block intervals, not multiple-test adjusted',fontsize=11)
fig.savefig(P/'rsi_market_comparison.png',dpi=160)
plt.close(fig)
singles=pd.concat([pd.read_parquet(P/'fullgrid'/f'single_{m}.parquet') for m in ['kospi','kosdaq']],ignore_index=True)
singles.to_csv(P/'all_single_results.csv',index=False,encoding='utf-8-sig')
key=d[d.a.isin(labels+['market_cap__q5','annual_pe_approx__abs(0,5]'])&d.b.isna()]
key.to_csv(P/'key_results.csv',index=False,encoding='utf-8-sig')
print('Created RSI chart, key_results.csv and all_single_results.csv:',len(singles),'single-period rows')
