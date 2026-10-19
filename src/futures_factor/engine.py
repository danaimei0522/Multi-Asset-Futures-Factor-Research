"""Daily event engine. Standard library only. See docs/ASSUMPTIONS.md."""
from dataclasses import dataclass, asdict
from datetime import date
import csv
import math

@dataclass(frozen=True)
class Bar:
    date: str
    symbol: str
    contract: str
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass(frozen=True)
class Spec:
    multiplier: float
    tick: float
    margin_rate: float
    fee_per_lot: float
    close_today_fee_per_lot: float
    slippage_ticks: int

@dataclass(frozen=True)
class Config:
    initial_cash: float = 1_000_000
    window: int = 20
    warmup: int = 60
    atr_multiple: float = 3.0
    lots: int = 2
    periods_per_year: int = 252
    symbols: tuple[str, ...] = ("RB", "AU", "CU", "AG")

@dataclass
class Position:
    contract: str
    side: int
    qty: int
    mark: float
    stop: float
    opened: str

def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def canonical_date(value):
    if not isinstance(value, str):
        raise ValueError('Date must be YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('Date must be YYYY-MM-DD') from exc
    if parsed.isoformat() != value:
        raise ValueError('Date must be canonical YYYY-MM-DD')
    return value

def load_calendar(path):
    with open(path, newline='', encoding='utf-8') as f:
        return [canonical_date(r['date']) for r in csv.DictReader(f)]


def signal(history, cfg):
    """History includes signal day's completed bar; breakout excludes that bar."""
    if len(history) < max(cfg.warmup, cfg.window + 1):
        return 0, None
    w = cfg.window
    now = history[-1]
    ma = sum(b.close for b in history[-w:]) / w
    previous = history[-w-1:-1]
    trs = [max(history[i].high-history[i].low,
               abs(history[i].high-history[i-1].close),
               abs(history[i].low-history[i-1].close))
           for i in range(len(history)-w, len(history))]
    atr = sum(trs) / w
    if now.volume <= 0 or atr <= 0:
        return 0, atr
    if now.close > ma and now.close > max(b.high for b in previous):
        return 1, atr
    if now.close < ma and now.close < min(b.low for b in previous):
        return -1, atr
    return 0, atr

def load_bars(path):
    with open(path, newline='', encoding='utf-8') as f:
        return [Bar(r['date'], r['symbol'], r['contract'],
                    *(float(r[k]) for k in ('open','high','low','close','volume')))
                for r in csv.DictReader(f)]

def load_routes(path):
    routes = {}
    with open(path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            canonical_date(r['date']); canonical_date(r['known_on'])
            if r['known_on'] >= r['date']:
                raise ValueError('Route must be known before execution date')
            key = (r['date'], r['symbol'])
            if key in routes:
                raise ValueError('Duplicate route')
            routes[key] = r['contract']
    return routes

class Engine:
    def __init__(self, specs, cfg=Config()):
        if (not finite(cfg.initial_cash) or cfg.initial_cash <= 0
            or not finite(cfg.atr_multiple) or cfg.atr_multiple <= 0
            or any(type(v) is not int or v < 1 for v in
                   (cfg.window, cfg.warmup, cfg.lots, cfg.periods_per_year))):
            raise ValueError('Invalid configuration: finite positive values and integer counts required')
        if (not isinstance(cfg.symbols, (tuple, list)) or not cfg.symbols
            or any(v not in ('RB', 'AU', 'CU', 'AG') for v in cfg.symbols)
            or len(set(cfg.symbols)) != len(cfg.symbols)):
            raise ValueError('Invalid configured research symbols')
        for s in specs.values():
            values = asdict(s).values()
            if (not all(finite(v) for v in values) or s.multiplier <= 0
                or s.tick <= 0 or not 0 < s.margin_rate <= 1
                or min(s.fee_per_lot, s.close_today_fee_per_lot) < 0
                or type(s.slippage_ticks) is not int or s.slippage_ticks < 0):
                raise ValueError('Invalid specification')
        self.specs, self.cfg = specs, cfg

    def run(self, bars, routes, start=None, end=None, *, calendar):
        """Routes key=(execution date,symbol), value=individual contract.
        Earlier rows are warmup only. No forced end liquidation.
        One Engine.run call has no state carried from any earlier call.
        """
        cfg = self.cfg
        sessions = list(calendar)
        for day in sessions: canonical_date(day)
        if not sessions or sessions != sorted(set(sessions)):
            raise ValueError('Calendar must be nonempty, ordered and unique')
        for bound in (start, end):
            if bound is not None: canonical_date(bound)
        if start is not None and end is not None and start > end:
            raise ValueError('Start must not exceed end')
        active_days = [d for d in sessions if (start is None or d >= start)
                       and (end is None or d <= end)]
        if not active_days:
            raise ValueError('No calendar sessions in requested interval')
        if start is not None and start < sessions[0]:
            raise ValueError('Calendar does not cover start boundary')
        if end is not None and end > sessions[-1]:
            raise ValueError('Calendar does not cover end boundary')
        session_index = {d: i for i, d in enumerate(sessions)}
        for (day, symbol), contract in routes.items():
            canonical_date(day)
            if day not in session_index or symbol not in cfg.symbols:
                raise ValueError('Route outside calendar/research universe')
            if not isinstance(contract, str) or not contract.strip():
                raise ValueError('Invalid route contract')
        rows = sorted(bars, key=lambda b:(b.date,b.symbol,b.contract))
        by_day, seen, owners = {}, set(), {}
        for b in rows:
            canonical_date(b.date)
            if b.date not in session_index:
                raise ValueError('Bar outside explicit calendar')
            if not isinstance(b.contract, str) or not b.contract.strip():
                raise ValueError('Invalid contract ID')
            key=(b.date,b.contract)
            if key in seen: raise ValueError('Duplicate contract bar')
            seen.add(key)
            if b.symbol not in cfg.symbols: raise ValueError('Symbol outside research universe')
            if owners.setdefault(b.contract,b.symbol) != b.symbol:
                raise ValueError('Contract symbol changed')
            if b.contract not in self.specs: raise ValueError('Missing contract specification')
            if (not all(finite(x) for x in (b.open,b.high,b.low,b.close,b.volume))
                or min(b.open,b.low,b.close) <= 0 or b.volume < 0
                or b.low > min(b.open,b.close) or b.high < max(b.open,b.close)):
                raise ValueError('Invalid OHLCV')
            by_day.setdefault(b.date,{})[b.contract]=b
        # Validate the declared universe even when no position has ever existed.
        for day in sessions:
            available = by_day.get(day, {})
            for symbol in cfg.symbols:
                if not any(b.symbol == symbol for b in available.values()):
                    raise ValueError(f'Missing symbol/session: {day} {symbol}')
                if day in active_days:
                    contract = routes.get((day, symbol))
                    if contract not in available or available[contract].symbol != symbol:
                        raise ValueError(f'Missing/mismatched daily route/bar: {day} {symbol}')
        # Listed/delisted tails are permitted; internal holes are not.
        contract_indices = {}
        for b in rows:
            contract_indices.setdefault(b.contract, []).append(session_index[b.date])
        for contract, indices in contract_indices.items():
            if indices != list(range(indices[0], indices[-1] + 1)):
                raise ValueError(f'Non-contiguous contract history: {contract}')
        cash=cfg.initial_cash
        history={}; positions={}; fills=[]; equity=[]; events=[]
        def margin():
            return sum(p.qty*p.mark*self.specs[p.contract].multiplier*
                       self.specs[p.contract].margin_rate for p in positions.values())
        def trade(day, symbol, contract, side, qty, reference, reason, closing=False, atr=None):
            nonlocal cash
            s=self.specs[contract]
            raw=reference+side*s.tick*s.slippage_ticks
            price=(math.ceil(raw/s.tick-1e-10) if side>0 else math.floor(raw/s.tick+1e-10))*s.tick
            if price <= 0: raise ValueError('Nonpositive simulated fill')
            fee_rate=s.fee_per_lot
            if closing and positions[symbol].opened==day:
                fee_rate=s.close_today_fee_per_lot
            fee=qty*fee_rate
            if not closing:
                required=qty*reference*s.multiplier*s.margin_rate
                # All new positions are immediately marked to the same open reference.
                slip_loss=qty*abs(price-reference)*s.multiplier
                if cash-fee-slip_loss < margin()+required:
                    events.append(dict(date=day,symbol=symbol,reason='insufficient_margin'))
                    return False
                stop=price-side*cfg.atr_multiple*atr
                positions[symbol]=Position(contract,side,qty,reference,stop,day)
                cash-=fee+slip_loss
            else:
                p=positions.pop(symbol)
                cash+=p.side*qty*(price-p.mark)*s.multiplier-fee
            fills.append(dict(date=day,symbol=symbol,contract=contract,side=side,
                              qty=qty,price=price,fee=fee,reason=reason))
            return True
        for day, today in sorted(by_day.items()):
            active=(start is None or day>=start) and (end is None or day<=end)
            if end and day>end: break
            if active:
                # Strict input policy prevents silent stale-price carry/imaginary liquidation.
                symbols=sorted(cfg.symbols)
                for symbol in symbols:
                    if (day,symbol) not in routes: raise ValueError('Missing daily route')
                    contract=routes[day,symbol]
                    if contract not in today or today[contract].symbol!=symbol:
                        raise ValueError('Missing/mismatched routed bar')
                    if symbol in positions and positions[symbol].contract not in today:
                        raise ValueError('Missing held contract bar')
                def checked_history(contract):
                    h = history.get(contract, [])
                    previous_index = session_index[day] - 1
                    if h and (previous_index < 0 or h[-1].date != sessions[previous_index]):
                        raise ValueError(f'Stale contract history: {day} {contract}')
                    return h
                # Validate target and held history before any orders on this session.
                for symbol in symbols:
                    checked_history(routes[day, symbol])
                    if symbol in positions:
                        checked_history(positions[symbol].contract)
                # Settle all existing holdings to open before allocating shared funds.
                for p in positions.values():
                    s=self.specs[p.contract]; b=today[p.contract]
                    cash+=p.side*p.qty*(b.open-p.mark)*s.multiplier
                    p.mark=b.open
                stopped=set()
                # Old positions: gap stops have priority, then roll/signal exits.
                for symbol in sorted(list(positions)):
                    p=positions[symbol]; b=today[p.contract]
                    direction,atr=signal(checked_history(p.contract),cfg)
                    gap=(p.side==1 and b.open<=p.stop) or (p.side==-1 and b.open>=p.stop)
                    roll=routes[day,symbol]!=p.contract
                    if gap or roll or direction!=p.side:
                        reason='gap_stop' if gap else ('roll_close' if roll else 'signal_exit')
                        trade(day,symbol,p.contract,-p.side,p.qty,b.open,reason,True)
                        if gap:
                            stopped.add(symbol)
                            if roll:
                                events.append(dict(date=day,symbol=symbol,
                                                   reason='roll_entry_blocked_by_gap_stop'))
                # Deterministic alphabetical priority: AG, AU, CU, RB.
                for symbol in symbols:
                    if symbol in positions or symbol in stopped: continue
                    contract=routes[day,symbol]; b=today[contract]
                    h=checked_history(contract)
                    if not h:
                        events.append(dict(date=day,symbol=symbol,reason='no_previous_session_bar'))
                        continue
                    direction,atr=signal(h,cfg)
                    if direction:
                        trade(day,symbol,contract,direction,cfg.lots,b.open,'signal_entry',atr=atr)
                if not finite(cash) or cash <= 0 or cash + 1e-9 < margin():
                    raise ValueError('Open margin/equity breach: run invalid')
                # Resting stops including newly filled positions; no same-day re-entry.
                for symbol in sorted(list(positions)):
                    p=positions[symbol]; b=today[p.contract]
                    hit=(p.side==1 and b.low<=p.stop) or (p.side==-1 and b.high>=p.stop)
                    if hit:
                        entry_gap = p.opened == day and (
                            (p.side == 1 and b.open <= p.stop) or
                            (p.side == -1 and b.open >= p.stop))
                        reference = b.open if entry_gap else p.stop
                        reason = 'entry_gap_stop' if entry_gap else 'intraday_stop'
                        trade(day,symbol,p.contract,-p.side,p.qty,reference,reason,True)
                for p in positions.values():
                    b=today[p.contract]; s=self.specs[p.contract]
                    cash+=p.side*p.qty*(b.close-p.mark)*s.multiplier
                    p.mark=b.close
                equity.append(dict(date=day,equity=cash,margin=margin()))
                if not finite(cash) or cash <= 0 or cash + 1e-9 < margin():
                    events.append(dict(date=day,symbol='PORTFOLIO',reason='margin_breach_run_invalid'))
                    raise ValueError('Margin breach: liquidation/financing model required')
            for contract,b in today.items(): history.setdefault(contract,[]).append(b)
        return dict(status='independent_simulation_not_platform_replication',
                    equity=equity,fills=fills,events=events,
                    calendar=sessions,research_symbols=list(cfg.symbols),
                    open_positions={s:asdict(p) for s,p in positions.items()},
                    metrics=metrics(equity,cfg.initial_cash,cfg.periods_per_year))

def metrics(curve, initial, annual=252):
    if not finite(initial) or initial <= 0 or type(annual) is not int or annual < 1:
        raise ValueError('Invalid metric baseline/annualization')
    if any(not finite(r['equity']) or r['equity'] <= 0 for r in curve):
        raise ValueError('Metrics require finite positive equity')
    values=[initial]+[r['equity'] for r in curve]
    if len(values)<2: return {}
    returns=[b/a-1 for a,b in zip(values,values[1:])]
    mean=sum(returns)/len(returns)
    variance=sum((r-mean)**2 for r in returns)/(len(returns)-1) if len(returns)>1 else 0
    peak=initial; dd=0
    for v in values:
        peak=max(peak,v); dd=max(dd,1-v/peak)
    return dict(total_return=values[-1]/initial-1,
                annualized_return=(values[-1]/initial)**(annual/len(returns))-1,
                sharpe=mean/math.sqrt(variance)*math.sqrt(annual) if variance else None,
                max_drawdown=dd, sessions=len(returns))
