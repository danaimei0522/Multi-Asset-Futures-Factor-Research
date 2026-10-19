"""Run from project root; no network, platform SDK, or third-party dependency."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from futures_factor.engine import Config, Spec, Engine, load_bars, load_routes, load_calendar
p=argparse.ArgumentParser()
p.add_argument('--bars',required=True); p.add_argument('--routes',required=True)
p.add_argument('--calendar',required=True)
p.add_argument('--config',required=True); p.add_argument('--output',required=True)
a=p.parse_args()
c=json.loads(Path(a.config).read_text())
r=Engine({k:Spec(**v) for k,v in c['specs'].items()},Config(**c['strategy'])).run(
    load_bars(a.bars),load_routes(a.routes),c.get('start'),c.get('end'),calendar=load_calendar(a.calendar))
r['run_config']=c
import hashlib, platform
r['provenance']={'python':platform.python_version(),'inputs_sha256':{
    str(x):hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in (a.bars,a.routes,a.config,a.calendar)},
    'engine_sha256':hashlib.sha256((Path(__file__).resolve().parents[1]/'src/futures_factor/engine.py').read_bytes()).hexdigest()}
Path(a.output).parent.mkdir(parents=True,exist_ok=True)
Path(a.output).write_text(json.dumps(r,indent=2,allow_nan=False),encoding='utf-8')
print('Independent simulation saved:',a.output)
