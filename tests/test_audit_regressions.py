"""Synthetic arithmetic and event-order regressions; no market performance claims."""
import unittest
from dataclasses import replace
from futures_factor.engine import Bar, Config, Engine, Spec, metrics
from test_engine import bars, S


def execute(bs, *, universe=('RB',), calendar=None, routes=None, cfg=None, spec=S, start=None):
    return Engine({b.contract:spec for b in bs},cfg or Config(symbols=universe)).run(
        bs, routes if routes is not None else {(b.date,b.symbol):b.contract for b in bs},
        start=start,calendar=calendar if calendar is not None else sorted({b.date for b in bs}))


class AuditRegressions(unittest.TestCase):
    def test_shared_margin_rejects_third_order_instead_of_invalidating_run(self):
        bs=sum([bars(61,symbol=s,contract=s+'TEST') for s in ('AG','AU','CU')],[])
        r=execute(bs,cfg=Config(initial_cash=990,symbols=('AG','AU','CU')),
                  spec=Spec(10,.5,.1,1,3,1))
        self.assertEqual([f['symbol'] for f in r['fills']],['AG','AU'])
        self.assertEqual(r['events'][-1]['reason'],'insufficient_margin')
        self.assertEqual(r['events'][-1]['symbol'],'CU')
        self.assertAlmostEqual(r['equity'][-1]['equity'],966)
        self.assertAlmostEqual(r['equity'][-1]['margin'],640)

    def test_short_margin_uses_market_mark_not_lower_sell_fill(self):
        r=execute(bars(61,short=True),cfg=Config(initial_cash=291.5,symbols=('RB',)),
                  spec=Spec(10,.5,.1,1,3,1))
        self.assertEqual(r['fills'],[])  # 280 market margin + 12 fee/slip = 292

    def test_slippage_charged_once_on_close_mark(self):
        r=execute(bars(61),spec=Spec(10,.5,.1,1,3,1))
        self.assertAlmostEqual(r['equity'][-1]['equity'],1_000_000-2-10)

    def test_missing_entire_symbol_rejected_with_default_universe(self):
        bs=bars(61)
        with self.assertRaisesRegex(ValueError,'Missing symbol/session'):
            Engine({'RBTEST':S}).run(bs,{(b.date,'RB'):b.contract for b in bs},calendar=[b.date for b in bs])

    def test_missing_whole_session_rejected(self):
        bs=bars(65); calendar=[b.date for b in bs]
        with self.assertRaisesRegex(ValueError,'Missing symbol/session'):
            execute(bs[:30]+bs[31:],calendar=calendar)

    def test_one_symbol_missing_day_rejected(self):
        rb=bars(65); au=bars(65,symbol='AU',contract='AUTEST')
        with self.assertRaisesRegex(ValueError,'Missing symbol/session'):
            execute(rb+au[:30]+au[31:],universe=('RB','AU'))

    def test_gap_in_warmup_rejected_even_if_other_contract_covers_day(self):
        old=bars(65); new=bars(65,contract='RBNEW')
        with self.assertRaisesRegex(ValueError,'Non-contiguous contract history'):
            execute(old[:20]+old[21:]+new)

    def test_missing_previous_held_bar_rejected(self):
        old=bars(65); extra=bars(65,contract='RBNEW')
        route={(b.date,'RB'):('RBNEW' if i==61 else 'RBTEST') for i,b in enumerate(old)}
        with self.assertRaisesRegex(ValueError,'Non-contiguous contract history'):
            execute(old[:61]+old[62:]+extra,routes=route)

    def test_stale_route_history_rejected(self):
        old=bars(65); new=bars(65,contract='RBNEW'); new=new[:61]+new[64:]
        route={(b.date,'RB'):('RBNEW' if i==64 else 'RBTEST') for i,b in enumerate(old)}
        with self.assertRaisesRegex(ValueError,'Non-contiguous contract history'):
            execute(old+new,routes=route)

    def test_newly_listed_contract_short_history_remains_no_entry(self):
        old=bars(65); new=bars(65,contract='RBNEW')[62:]
        route={(b.date,'RB'):('RBNEW' if i>=62 else 'RBTEST') for i,b in enumerate(old)}
        r=execute(old+new,routes=route)
        self.assertEqual([f['reason'] for f in r['fills']],['signal_entry','roll_close'])

    def test_invalid_configs(self):
        for kw in ({'initial_cash':float('nan')},{'initial_cash':float('inf')},
                   {'atr_multiple':float('nan')},{'lots':2.5},{'lots':True},
                   {'window':20.0},{'warmup':0},{'symbols':('RB','RB')}):
            with self.subTest(kw=kw),self.assertRaises(ValueError): Engine({'RBTEST':S},Config(**kw))

    def test_bad_dates_and_ranges(self):
        bs=bars()
        for kwargs in ({'start':'20240101'},{'start':'2024-03-01','end':'2024-01-01'},
                       {'end':'2025-01-01'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                Engine({'RBTEST':S},Config(symbols=('RB',))).run(bs,{},calendar=[b.date for b in bs],**kwargs)

    def test_invalid_calendar(self):
        bs=bars(2)
        for cal in ([],[bs[0].date]*2,[bs[1].date,bs[0].date],['20240101']):
            with self.subTest(cal=cal),self.assertRaises(ValueError): execute(bs,calendar=cal)

    def test_abnormal_bar_rejected(self):
        b=bars(1)[0]
        for change in ({'close':float('nan')},{'volume':-1},{'open':0},{'high':90},{'date':'20240101'}):
            with self.subTest(change=change),self.assertRaises(ValueError): execute([replace(b,**change)])

    def test_invalid_metrics_rejected(self):
        for x in (0,-1,float('nan'),float('inf')):
            with self.subTest(equity=x),self.assertRaises(ValueError): metrics([{'equity':x}],100)

    def test_gap_stop_roll_conflict_long_and_short(self):
        for short in (False,True):
            old=bars(63,short=short); new=bars(63,contract='RBNEW',short=short)
            price=160 if short else 140
            old[61]=replace(old[61],open=price,high=price+.5,low=price-.5,close=price)
            route={(b.date,'RB'):('RBNEW' if i>=61 else 'RBTEST') for i,b in enumerate(old)}
            r=execute(old+new,routes=route)
            dayfills=[f for f in r['fills'] if f['date']==old[61].date]
            with self.subTest(short=short):
                self.assertEqual([f['reason'] for f in dayfills],['gap_stop'])
                self.assertEqual(dayfills[0]['price'],price)
                self.assertEqual(sum(e['reason']=='roll_entry_blocked_by_gap_stop' for e in r['events']),1)
                self.assertTrue(any(f['contract']=='RBNEW' and f['date']==old[62].date for f in r['fills']))

    def test_old_intraday_stop_not_used_after_open_roll(self):
        old=bars(62); new=bars(62,contract='RBNEW')
        old[61]=replace(old[61],low=140)  # old stop would be crossed only after roll exit
        route={(b.date,'RB'):('RBNEW' if i==61 else 'RBTEST') for i,b in enumerate(old)}
        r=execute(old+new,routes=route)
        f=[f for f in r['fills'] if f['date']==old[61].date]
        self.assertEqual([x['reason'] for x in f],['roll_close','signal_entry'])
        self.assertEqual(f[0]['price'],161)

    def test_new_contract_stop_after_roll_uses_its_own_price(self):
        old=bars(62); new=bars(62,contract='RBNEW')
        new[61]=replace(new[61],low=140)
        route={(b.date,'RB'):('RBNEW' if i==61 else 'RBTEST') for i,b in enumerate(old)}
        r=execute(old+new,routes=route)
        f=[f for f in r['fills'] if f['date']==old[61].date]
        self.assertEqual([x['reason'] for x in f],['roll_close','signal_entry','intraday_stop'])
        self.assertEqual(f[-1]['contract'],'RBNEW'); self.assertEqual(f[-1]['fee'],6)

    def test_insufficient_roll_funds_closes_old_and_rejects_new(self):
        old=bars(62); new=[replace(b,open=b.open*10,high=b.high*10,low=b.low*10,close=b.close*10)
                          for b in bars(62,contract='RBNEW')]
        route={(b.date,'RB'):('RBNEW' if i==61 else 'RBTEST') for i,b in enumerate(old)}
        r=execute(old+new,routes=route,cfg=Config(initial_cash=1000,symbols=('RB',)))
        self.assertEqual([f['reason'] for f in r['fills']],['signal_entry','roll_close'])
        self.assertEqual(r['open_positions'],{}); self.assertEqual(r['events'][-1]['reason'],'insufficient_margin')

    def test_gap_stop_and_signal_exit_close_only_once(self):
        bs=bars(62); bs[60]=replace(bs[60],volume=0)
        bs[61]=replace(bs[61],open=140,high=141,low=139,close=140)
        r=execute(bs)
        self.assertEqual([f['reason'] for f in r['fills']],['signal_entry','gap_stop'])

    def test_no_future_read_in_roll_old_high_low(self):
        old=bars(62); new=bars(62,contract='RBNEW')
        route={(b.date,'RB'):('RBNEW' if i==61 else 'RBTEST') for i,b in enumerate(old)}
        a=execute(old+new,routes=route)
        old[61]=replace(old[61],low=1,high=10000)
        b=execute(old+new,routes=route)
        self.assertEqual(a['fills'],b['fills']); self.assertEqual(a['equity'],b['equity'])

    def test_close_equity_breach_invalidates_run(self):
        bs=bars(62); bs[-1]=replace(bs[-1],open=140,high=141,low=139,close=140)
        with self.assertRaisesRegex(ValueError,'breach'):
            execute(bs,cfg=Config(initial_cash=325,symbols=('RB',)))

    def test_new_entry_stop_already_breached_uses_open_not_unavailable_stop(self):
        # Extreme artificial slip puts the entry-based stop above market open.
        # The exit cannot assume sale at that higher stop.
        r=execute(bars(61),spec=Spec(10,.5,.1,1,3,20))
        f=r['fills']
        self.assertEqual(len(f),2)
        self.assertEqual(f[0]['price'],170)
        self.assertEqual(f[1]['reason'],'entry_gap_stop')
        self.assertEqual(f[1]['price'],150)  # open 160 minus 10 adverse sell slip
        self.assertAlmostEqual(r['equity'][-1]['equity'],1_000_000-400-2-6)

    def test_atr_twenty_true_ranges_include_previous_close_gap(self):
        from futures_factor.engine import signal
        bs=bars(60)
        # Normal 20-period TR is 1.5; final gap adds 10 to last TR.
        b=bs[-1]; bs[-1]=replace(b,open=b.open+10,high=b.high+10,low=b.low+10,close=b.close+10)
        direction,atr=signal(bs,Config())
        self.assertEqual(direction,1); self.assertAlmostEqual(atr,2.0)

    def test_fixed_stop_does_not_trail_after_favorable_move(self):
        bs=bars(64)
        # Entry 160, ATR 1.5, fixed stop 155.5, despite subsequent higher closes.
        bs[-1]=replace(bs[-1],low=155)
        r=execute(bs)
        self.assertEqual(r['fills'][-1]['reason'],'intraday_stop')
        self.assertAlmostEqual(r['fills'][-1]['price'],155.5)

    def test_short_stop_uses_buy_slip_and_close_today_fee(self):
        bs=bars(61,short=True); bs[-1]=replace(bs[-1],high=150)
        r=execute(bs,spec=Spec(10,.5,.1,1,3,1))
        self.assertEqual(r['fills'][0]['price'],139.5)
        self.assertEqual(r['fills'][-1]['price'],144.5)
        self.assertEqual(r['fills'][-1]['fee'],6)
        self.assertAlmostEqual(r['equity'][-1]['equity'],1_000_000-100-8)

    def test_calendar_csv_loader(self):
        import tempfile
        from pathlib import Path
        from futures_factor.engine import load_calendar
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'calendar.csv'; p.write_text('date\n2024-01-01\n2024-01-02\n')
            self.assertEqual(load_calendar(p),['2024-01-01','2024-01-02'])
            p.write_text('date\n20240101\n')
            with self.assertRaises(ValueError): load_calendar(p)
