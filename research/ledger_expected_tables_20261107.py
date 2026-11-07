# 독립 손계산: 합성 고정자료 F1 (slots=2, hold=3, entry_lag=1, 비용 왕복 0.5% = 한쪽 0.25%, 원 미만 절사) — S_b(1주 내림) 모드
import math
R=0.0025
def fee(a): return math.floor(a*R)
CAP=3_000_000
def run(prices, picks, days, skip_days=(), gone_from=None, susp=()):
    # prices: {ticker:{day:close}}; picks: {day: ticker}; days: 달력(본표)
    cash=CAP; pos={}  # ticker -> dict(qty, entry_day, exit_due_idx, last)
    rows=[]
    for i,d in enumerate(days):
        ev=[]
        # 1) 만기 매도 (그날 종가) — 정지면 지연
        for t,p in list(pos.items()):
            if i>=p['due']:
                if (t,d) in susp:
                    ev.append(f"EXIT 지연 {t}"); continue
                px = prices[t].get(d)
                if px is None:  # gone
                    px = p['last']*0.1 if gone_from and d>=gone_from else p['last']
                amt=p['qty']*px; f=fee(amt); cash+=amt-f
                ev.append(f"SELL {t} {p['qty']}주×{px:,.0f}={amt:,.0f} 수수료 {f:,}")
                del pos[t]
        # 2) 진입: 전날(추천일) 목록 → 오늘 종가
        if i>0 and days[i-1] in picks:
            t=picks[days[i-1]]; px=prices[t].get(d)
            nav_prev=rows[-1]['nav'] if rows else CAP
            budget=nav_prev//2  # NAV/슬롯(원 단위 내림)
            if px is None or (t,d) in susp:
                ev.append(f"SKIP {t} not_tradable")
            else:
                qty=budget//px
                if qty==0: ev.append(f"SKIP {t} budget_lt_1_share(예산 {budget:,} < {px:,})")
                else:
                    amt=qty*px; f=fee(amt); cash-=amt+f
                    pos[t]=dict(qty=qty,due=i+3,last=px)
                    ev.append(f"BUY {t} {qty}주×{px:,}={amt:,} 수수료 {f:,} 잔돈 {budget-amt:,}")
        # 3) 평가
        held=0
        for t,p in pos.items():
            px=prices[t].get(d)
            if px is not None: p['last']=px
            mark = p['last']*0.1 if (px is None and gone_from and d>=gone_from) else p['last']
            held+=p['qty']*mark
        nav=cash+held
        rows.append(dict(day=d,cash=cash,held=held,nav=nav,ev=' · '.join(ev)))
    return rows
def show(name, rows):
    print(f"\n### {name}")
    print("| 날 | 현금 | 보유평가 | NAV | 이벤트 |\n|---|---|---|---|---|")
    for r in rows: print(f"| {r['day']} | {r['cash']:,.0f} | {r['held']:,.0f} | {r['nav']:,.0f} | {r['ev']} |")
D=[f"D{i}" for i in range(1,11)]
flat=lambda v:{d:v for d in D}
# S1 정상: A 10,000 → D5 11,000 이후 11,000
A={**flat(10_000), **{d:11_000 for d in D[4:]}}
show("S1 정상 (D1 추천 A → D2 10,000 매수 150주 → D5 11,000 매도)", run({'A':A},{'D1':'A'},D))
# S2 0주
show("S2 0주 (B 2,000,000원)", run({'B':flat(2_000_000)},{'D1':'B'},D))
# S3 잔돈
show("S3 잔돈 (C 7,000원 → 214주, 잔돈 2,000)", run({'C':flat(7_000)},{'D1':'C'},D))
# S4 정지 중 만기: A, D5 정지 → D6 청산 11,500
A4={**flat(10_000), **{d:11_500 for d in D[5:]}}; A4['D5']=10_000
show("S4 정지 중 만기 (D5 정지 → D6 11,500 청산, 지연 1일)", run({'A':A4},{'D1':'A'},D, susp={('A','D5')}))
# S5 결손일: 본표에 D4 없음 → 달력 9일
D5=[d for d in D if d!='D4']
show("S5 결손일 (본표 달력에 D4 없음 → 만기 = 달력상 3거래일 뒤 = D6)", run({'A':A},{'D1':'A'},D5))
# S9 상폐: A 시세 D6부터 없음(gone), 만기 D5 는 정상 청산이므로 hold 를 늘려 보기 위해 D3 추천 → D4 매수 → 만기 D7 (시세 없음) → 마지막가×0.1
A9={d:10_000 for d in D[:5]}
show("S9 상폐 (D3 추천 → D4 매수 → D6~ 시세 없음 → D7 만기에 마지막가 10,000×0.1 로 청산)", run({'A':A9},{'D3':'A'},D, gone_from='D6'))
