"""Artificial trending bars for plumbing demonstrations; NOT market data."""
import csv,json
from pathlib import Path
from datetime import date,timedelta
p=Path('outputs/synthetic'); p.mkdir(parents=True,exist_ok=True)
with (p/'bars.csv').open('w',newline='') as f, (p/'routes.csv').open('w',newline='') as g:
    b=csv.writer(f); r=csv.writer(g)
    b.writerow(['date','symbol','contract','open','high','low','close','volume'])
    r.writerow(['date','symbol','contract','known_on'])
    for i in range(90):
        d=date(2024,1,1)+timedelta(days=i)
        for symbol in ['RB','AU','CU','AG']:
            price=100+i
            b.writerow([d.isoformat(),symbol,symbol+'TEST',price,price+1.5,price-.5,price+1,100])
            r.writerow([d.isoformat(),symbol,symbol+'TEST',(d-timedelta(days=1)).isoformat()])
spec=dict(multiplier=10,tick=.5,margin_rate=.1,fee_per_lot=1,close_today_fee_per_lot=2,slippage_ticks=1)
(p/'config.json').write_text(json.dumps(dict(strategy=dict(initial_cash=1000000),specs={s+'TEST':spec for s in ['RB','AU','CU','AG']}),indent=2))
print('Artificial daily calendar and fictional specifications:',p)

with (p/'calendar.csv').open('w',newline='') as f:
    w=csv.writer(f); w.writerow(['date'])
    w.writerows([[(date(2024,1,1)+timedelta(days=i)).isoformat()] for i in range(90)])
