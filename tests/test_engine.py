import unittest
from datetime import date,timedelta
from dataclasses import replace
from futures_factor.engine import Bar,Spec,Config,Engine,signal,metrics

def bars(n=65,contract='RBTEST',symbol='RB',short=False):
    out=[]
    for i in range(n):
        x=200-i if short else 100+i
        out.append(Bar((date(2024,1,1)+timedelta(days=i)).isoformat(),symbol,contract,x,x+.5,x-.5,x,100))
    return out
S=Spec(10,.5,.1,1,3,0)
def run(bs,spec=S,cfg=Config(),routes=None):
    return Engine({b.contract:spec for b in bs},replace(cfg,symbols=tuple(sorted({b.symbol for b in bs})))).run(bs,routes or {(b.date,b.symbol):b.contract for b in bs},calendar=sorted({b.date for b in bs}))

class Tests(unittest.TestCase):
    def test_warmup(self):
        self.assertEqual(signal(bars(59),Config())[0],0)
        self.assertEqual(signal(bars(60),Config())[0],1)
    def test_short(self): self.assertEqual(signal(bars(60,short=True),Config())[0],-1)
    def test_volume(self):
        b=bars(60); q=b[-1]; b[-1]=Bar(q.date,q.symbol,q.contract,q.open,q.high,q.low,q.close,0)
        self.assertEqual(signal(b,Config())[0],0)
    def test_breakout_excludes_current(self):
        self.assertEqual(signal(bars(60),Config())[0],1)
    def test_equality_no_breakout(self):
        b=bars(60); q=b[-1]; x=b[-2].high
        b[-1]=Bar(q.date,q.symbol,q.contract,x,x,x,x,100)
        self.assertEqual(signal(b,Config())[0],0)
    def test_next_open_and_target(self):
        r=run(bars()); self.assertEqual(r['fills'][0]['date'],bars()[60].date)
        self.assertEqual(r['fills'][0]['price'],160)
        self.assertEqual(len(r['fills']),1); self.assertEqual(r['fills'][0]['qty'],2)
        self.assertAlmostEqual(r['equity'][-1]['equity'],1000000-2+2*4*10)
    def test_prefix_causality(self):
        a=run(bars(63)); b=run(bars(65))
        self.assertEqual(a['equity'],b['equity'][:63]); self.assertEqual(a['fills'],b['fills'])
    def test_signal_exit(self):
        b=bars(63); q=b[61]; b[61]=Bar(q.date,q.symbol,q.contract,161,162,160,161,0)
        r=run(b); self.assertEqual(r['fills'][1]['reason'],'signal_exit')
        self.assertEqual(r['fills'][1]['date'],b[62].date)
    def test_gap_stop(self):
        b=bars(62); q=b[-1]; b[-1]=Bar(q.date,q.symbol,q.contract,140,141,139,140,100)
        r=run(b); self.assertEqual(r['fills'][1]['reason'],'gap_stop')
        self.assertEqual(r['fills'][1]['price'],140)
    def test_same_day_stop_fee(self):
        b=bars(61); q=b[-1]; b[-1]=Bar(q.date,q.symbol,q.contract,160,161,150,160,100)
        r=run(b); self.assertEqual(r['fills'][1]['reason'],'intraday_stop')
        self.assertEqual(r['fills'][1]['fee'],6)
    def test_execution_day_volume_not_used_at_open(self):
        b=bars(61); q=b[-1]
        b[-1]=Bar(q.date,q.symbol,q.contract,q.open,q.high,q.low,q.close,0)
        self.assertEqual(len(run(b)['fills']),1)
    def test_route_availability(self):
        import tempfile
        from pathlib import Path
        from futures_factor.engine import load_routes
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'routes.csv'
            p.write_text('date,symbol,contract,known_on\n2024-01-02,RB,RBTEST,2024-01-02\n')
            with self.assertRaises(ValueError): load_routes(p)
    def test_short_pnl(self):
        r=run(bars(short=True))
        self.assertEqual(r['fills'][0]['side'],-1)
        self.assertAlmostEqual(r['equity'][-1]['equity'],1000000-2+80)
    def test_costs(self):
        a=run(bars()); b=run(bars(),Spec(10,.5,.1,2,3,1))
        self.assertLess(b['equity'][-1]['equity'],a['equity'][-1]['equity'])
    def test_margin_rejection(self): self.assertEqual(run(bars(),cfg=Config(initial_cash=10))['fills'],[])
    def test_roll_sequence(self):
        a=bars(); b=bars(contract='RBNEW'); allbars=a+b
        route={(x.date,'RB'):('RBTEST' if i<62 else 'RBNEW') for i,x in enumerate(a)}
        r=run(allbars,routes=route); f=[x for x in r['fills'] if x['date']==a[62].date]
        self.assertEqual([x['reason'] for x in f],['roll_close','signal_entry'])
        self.assertEqual([x['contract'] for x in f],['RBTEST','RBNEW'])
    def test_new_contract_warmup(self):
        a=bars(); b=bars(contract='RBNEW')[61:]; route={(x.date,'RB'):('RBTEST' if i<62 else 'RBNEW') for i,x in enumerate(a)}
        r=run(a+b,routes=route)
        self.assertEqual([x['reason'] for x in r['fills']],['signal_entry','roll_close'])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): run(bars()+bars()[:1])
    def test_missing_route(self):
        b=bars(); route={(x.date,'RB'):x.contract for x in b[:-1]}
        with self.assertRaises(ValueError): run(b,routes=route)
    def test_bad_ohlc(self):
        with self.assertRaises(ValueError): run([Bar('2024-01-01','RB','RBTEST',100,90,99,100,1)])
    def test_metrics(self):
        m=metrics([{'equity':110},{'equity':99}],100)
        self.assertAlmostEqual(m['total_return'],-.01); self.assertAlmostEqual(m['max_drawdown'],.1)
    def test_warmup_not_in_returns(self):
        b=bars(); r=Engine({'RBTEST':S},Config(symbols=('RB',))).run(b,{(x.date,'RB'):x.contract for x in b},start=b[60].date,calendar=[x.date for x in b])
        self.assertEqual(len(r['equity']),5); self.assertEqual(len(r['fills']),1)

if __name__=='__main__': unittest.main()
