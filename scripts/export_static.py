"""
Export everything the demo UI needs as static JSON so the site runs with no backend
(Vercel static hosting) — zero cold starts, zero dependencies at judging time.
The live API remains the real system; static mode is a faithful snapshot of its outputs.

  .venv/bin/python scripts/export_static.py   ->  web/public/static/*.json
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
OUT = ROOT / "web/public/static"; OUT.mkdir(parents=True, exist_ok=True)
from api import main as m
from api.narrative import template

def dump(name, obj): (OUT / f"{name}.json").write_text(json.dumps(obj, default=float)); print("wrote", name)

dump("health", {"ok": True, "model": m.METRICS.get("model"), "jev": False, "static": True})
dump("metrics", m.METRICS)
demo = m.demo_sessions(); dump("demo_sessions", demo)
replays = {d["session_id"]: m.session_payload(d["session_id"]) for d in demo}
alerts = m.alerts(25); dump("alerts", alerts)
for a in alerts[:12]:
    if a["session_id"] not in replays: replays[a["session_id"]] = m.session_payload(a["session_id"])
dump("replays", replays)
dump("accounts_flagged", m.accounts_flagged(15))
attacks = {k: [m.simulate(kind=k, seed=100 * i + 7) for i in range(4)] for k in ["A1", "A2", "A3", "A5", "A6", "A7"]}
dump("attacks", attacks)
# template narratives for every replay (LLM narratives are generated live when a key is configured)
narr = {}
for sid, r in replays.items():
    last = r["steps"][-1]
    narr[sid] = {"source": "template", "model": None, "text": template(dict(session_id=sid, user_id=r["user_id"], score=r["final_score"], n_events=r["n_events"],
                                                                        top_reasons=[x["feature"] for x in last["reasons"]], features=r["features"], decision=r["decision"]))}
dump("narratives", narr)
print("done:", len(replays), "replays,", sum(len(v) for v in attacks.values()), "attacks")
