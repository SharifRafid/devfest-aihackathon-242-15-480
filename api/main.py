"""
Second Thought scoring API.

  GET  /health
  GET  /metrics                         evaluation results from ml/models/metrics.json
  GET  /demo/sessions                   curated demo pool (human, hard-negative human, each attack archetype)
  GET  /sessions/{sid}/replay           per-event streaming scores + SHAP + policy decision (the Replay Theatre)
  POST /simulate/attack?kind=A1|A7|A3|A2|A6|A5   generate a brand-new attack session against a random user and score it live
  POST /score                           stateless: {user_id, events:[...]} -> same payload as replay
  POST /narrative                       analyst narrative grounded in evidence JSON (LLM or template)
  GET  /alerts                          analyst queue from the held-out test set
  GET  /accounts/flagged                account-role misuse (personal wallet acting as merchant/agent)

Every per-event score is computed by the same feature engine used in training (ml/features.py), on the
session prefix available at that moment — i.e. this is genuinely streaming logic, not a replay of stored labels.
"""
from __future__ import annotations
import json, sys, random
from pathlib import Path
import joblib, numpy as np, pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ml.features import MarkovFlow, UserProfile, session_features, session_summary_for_profile, FEATURE_NAMES, MONEY_API
from api.policy import decide, AUTOMATION_FEATS
from api.narrative import narrative
from api import jev_adapter

M = ROOT / "ml/models"; D = ROOT / "data/out"
app = FastAPI(title="Second Thought API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------- artefacts
clf = joblib.load(M / "session_clf.joblib"); iso = joblib.load(M / "isoforest.joblib"); aclf = joblib.load(M / "account_clf.joblib")
markov = MarkovFlow.from_dict(json.loads((M / "markov.json").read_text()))
THR = json.loads((M / "thresholds.json").read_text()); METRICS = json.loads((M / "metrics.json").read_text())
EV = pd.read_parquet(D / "events.parquet"); SE = pd.read_parquet(D / "sessions.parquet").set_index("session_id")
US = pd.read_parquet(D / "users.parquet").set_index("user_id"); ACC = pd.read_parquet(D / "accounts.parquet")
TEST_SCORES = pd.read_parquet(M / "test_scores.parquet")
DEVICE_COUNTS = SE.groupby("device_id").user_id.nunique().to_dict()
EV_BY_SID = {sid: g for sid, g in EV.sort_values(["session_id", "idx"]).groupby("session_id", sort=False)}
COLS = ["event", "dt_ms", "amount", "recipient_id", "pin_error", "ok", "ts"]
import shap
EXPL = shap.TreeExplainer(clf)
sys.path.insert(0, str(ROOT / "data"))
import generate as gen  # attack generators for /simulate


# ---------------------------------------------------------------- helpers
def profile_before(user_id: str, start_ts: int) -> tuple[UserProfile, set]:
    """Rebuild the user's profile from every session that started before start_ts (what the platform knew at that moment)."""
    prof, devices = UserProfile(), set()
    prior = SE[(SE.user_id == user_id) & (SE.start_ts < start_ts)].sort_values("start_ts")
    for sid, s in prior.iterrows():
        evs = EV_BY_SID[sid][COLS].to_dict("records")
        prof.update(**session_summary_for_profile(evs)); devices.add(s.device_id)
    return prof, devices


def top_shap(feat_row: dict, k=5):
    x = pd.DataFrame([feat_row])[FEATURE_NAMES]
    sv = EXPL.shap_values(x); sv = sv[1] if isinstance(sv, list) else sv
    s = pd.Series(sv[0], index=FEATURE_NAMES).sort_values(ascending=False)
    pos = s[s > 0].head(k)
    return [{"feature": f, "shap": round(float(v), 3), "value": round(float(feat_row[f]), 3)} for f, v in pos.items()]


def stream_score(events: list[dict], prof: UserProfile, new_device: int, device_user_count: int) -> dict:
    """Score every prefix. Returns the full timeline with the decision at each step."""
    thr = THR["session"]; steps = []; detect_at = None
    first_money = next((i for i, e in enumerate(events) if e["event"] in MONEY_API), -1)
    for k in range(1, len(events) + 1):
        f = session_features(events[:k], prof, markov, device_user_count, new_device)
        p = float(clf.predict_proba(pd.DataFrame([f])[FEATURE_NAMES])[:, 1][0])
        iso_s = float(-iso.score_samples(pd.DataFrame([f])[FEATURE_NAMES])[0])
        reasons = top_shap(f, 5) if p >= thr * 0.5 or k == len(events) else []
        dec = decide(p, f, [r["feature"] for r in reasons], THR)
        if detect_at is None and p >= thr: detect_at = k
        e = events[k - 1]
        steps.append(dict(k=k, event=e["event"], dt_ms=int(e["dt_ms"]), amount=float(e.get("amount") or 0), recipient=e.get("recipient_id", ""),
                          pin_error=int(e.get("pin_error", 0)), score=round(p, 4), iso=round(iso_s, 3), markov_nll=round(f["mk_mean_nll"], 3),
                          human_likeness=dec["human_likeness"], tier=dec["tier"], reasons=reasons,
                          automation_signals=[r["feature"] for r in reasons if r["feature"] in AUTOMATION_FEATS]))
    final = steps[-1]; ff = session_features(events, prof, markov, device_user_count, new_device)
    dec = decide(final["score"], ff, [r["feature"] for r in final["reasons"]], THR)
    jev = jev_adapter.decide_with_jev({"score": final["score"], "features": ff, "top_reasons": [r["feature"] for r in final["reasons"]]})
    return dict(steps=steps, final_score=final["score"], threshold=thr, detect_at=detect_at, first_money_k=(first_money + 1) if first_money >= 0 else None,
                stopped_before_money=bool(detect_at is not None and first_money >= 0 and detect_at <= first_money + 1),
                decision=dec, jev=jev, features=ff, n_events=len(events), profile=dict(n_prior_sessions=prof.n_sessions, usual_hour=prof.usual_hour(), known_recipients=len(prof.recipients)))


def session_payload(sid: str, reveal=True):
    if sid not in EV_BY_SID: raise HTTPException(404, "unknown session")
    g = EV_BY_SID[sid]; s = SE.loc[sid]; evs = g[COLS].to_dict("records")
    prof, devs = profile_before(s.user_id, int(s.start_ts))
    nd = int(s.device_id not in devs) if devs else 0
    out = stream_score(evs, prof, nd, DEVICE_COUNTS.get(s.device_id, 1))
    out.update(session_id=sid, user_id=s.user_id, persona=s.persona, device_id=s.device_id, new_device=nd, start_ts=int(s.start_ts),
               ground_truth=dict(label=s.label, archetype=s.archetype) if reveal else None)
    return out


# ---------------------------------------------------------------- routes
@app.get("/health")
def health(): return {"ok": True, "model": METRICS.get("model"), "jev": jev_adapter.available()}


@app.get("/metrics")
def metrics(): return METRICS


_DEMO_CACHE = {}
@app.get("/demo/sessions")
def demo_sessions(seed: int = 7):
    """One curated session per archetype + a plain human + a hard-negative human (big transfer to a new recipient that is NOT flagged)."""
    if seed in _DEMO_CACHE: return _DEMO_CACHE[seed]
    rng = random.Random(seed); ts = TEST_SCORES.reset_index()
    picks = []
    hum = ts[(ts.y == 0) & (ts.flag == 0) & (ts.n_events.between(12, 24))]
    picks.append(("Genuine user", hum.sample(1, random_state=seed).iloc[0].session_id))
    X = pd.read_parquet(M / "features.parquet")
    hn = ts[(ts.y == 0) & (ts.flag == 0)].merge(X[["frac_new_recipient", "amount_frac_cap"]], left_on="session_id", right_index=True)
    hn = hn[(hn.frac_new_recipient > 0) & (hn.amount_frac_cap > .3)]
    if len(hn): picks.append(("Genuine user, big payment to a NEW recipient (hard negative)", hn.sample(1, random_state=seed).iloc[0].session_id))
    names = {"A1_scripted_api": "Scripted ATO via reverse-engineered API", "A7_adaptive_scripted": "Adaptive attacker (human-like timing)",
             "A3_coerced_victim": "Coerced victim on a scam call", "A2_otp_relay_takeover": "OTP-relay takeover from new device",
             "A6_emulator_farm": "Emulator farm account", "A5_gambling_laundering": "Gambling / fake-purchase laundering"}
    for a, label in names.items():
        c = ts[(ts.archetype == a) & (ts.flag == 1) & (ts.n_events >= 3)]
        if len(c): picks.append((label, c.sample(1, random_state=seed).iloc[0].session_id))
    out = []
    for label, sid in picks:
        s = SE.loc[sid]
        out.append(dict(label=label, session_id=sid, user_id=s.user_id, persona=s.persona, archetype=s.archetype, n_events=int(s.n_events), money_total=float(s.money_total)))
    _DEMO_CACHE[seed] = out
    return out


@app.get("/sessions/{sid}/replay")
def replay(sid: str): return session_payload(sid)


@app.post("/simulate/attack")
def simulate(kind: str = Query("A1", pattern="^(A1|A2|A3|A5|A6|A7)$"), seed: int | None = None):
    """Generate a fresh attack right now against a random held-out user, then score it with the streaming engine."""
    rng = np.random.default_rng(seed); test_users = US[US.split == "test"]
    uid = str(rng.choice(test_users.index)); u = US.loc[uid].to_dict(); u["user_id"] = uid; u["devices"] = list(u["devices"]); u["recipients"] = list(u["recipients"])
    persona = next(p for p in gen.PERSONAS if p.name == u["persona"])
    start = int(SE[SE.user_id == uid].start_ts.max()) + 3_600_000
    own = str(rng.choice(u["devices"])); fresh = f"D{rng.integers(0, 1 << 30):08x}"
    if kind in ("A1", "A7"): b = gen.a1_scripted(rng, u, start, persona, fresh, adaptive=(kind == "A7"))
    elif kind == "A2": b = gen.a2_otp_relay(rng, u, start, persona, fresh)
    elif kind == "A3": b = gen.a3_coerced(rng, u, start, persona, own)
    elif kind == "A5": b = gen.a5_gambling(rng, u, start, persona, own)
    else: b = gen.a6_emulator(rng, u, start, persona, "EMU_LIVE01", farm_seed=7)
    evs = [{k: e[k] for k in COLS} for e in b.events]
    prof, devs = profile_before(uid, start)
    out = stream_score(evs, prof, int(b.dev not in devs), 25 if kind == "A6" else DEVICE_COUNTS.get(b.dev, 1))
    out.update(session_id=b.sid, user_id=uid, persona=u["persona"], device_id=b.dev, start_ts=start, ground_truth=dict(label="fraud", archetype=b.arch), simulated=True)
    return out


class ScoreReq(BaseModel):
    user_id: str
    events: list[dict]
    device_id: str | None = None


@app.post("/score")
def score(req: ScoreReq):
    if not req.events: raise HTTPException(400, "no events")
    start = int(req.events[0].get("ts", 0)); prof, devs = profile_before(req.user_id, start) if req.user_id in US.index else (UserProfile(), set())
    evs = [{**{c: 0 for c in COLS}, **e} for e in req.events]
    out = stream_score(evs, prof, int(req.device_id not in devs) if (req.device_id and devs) else 0, DEVICE_COUNTS.get(req.device_id, 1))
    out.update(session_id="adhoc", user_id=req.user_id)
    return out


class NarrReq(BaseModel):
    session_id: str
    user_id: str
    score: float
    n_events: int
    top_reasons: list[str]
    features: dict
    decision: dict


@app.post("/narrative")
def narr(req: NarrReq): return narrative(req.model_dump())


@app.get("/alerts")
def alerts(n: int = 25):
    ts = TEST_SCORES.reset_index(); q = ts[ts.flag == 1].assign(risk=lambda d: d.p * d.money_total.clip(lower=100)).sort_values("risk", ascending=False).head(n)
    rows = []
    for r in q.itertuples():
        s = SE.loc[r.session_id]
        rows.append(dict(session_id=r.session_id, user_id=r.user_id, score=round(float(r.p), 3), money_total=float(r.money_total), n_events=int(r.n_events),
                         start_ts=int(s.start_ts), persona=r.persona, hidden_archetype=r.archetype))
    return rows


@app.get("/accounts/flagged")
def accounts_flagged(n: int = 15):
    cols = THR["account_features"]; a = ACC[ACC.split == "test"].copy(); a["p"] = aclf.predict_proba(a[cols])[:, 1]
    top = a.sort_values("p", ascending=False).head(n)
    return [dict(user_id=r.user_id, persona=r.persona, p=round(float(r.p), 3), inbound_tx_30d=int(r.inbound_tx_30d), unique_senders_30d=int(r.unique_senders_30d),
                 cashout_count_30d=int(r.cashout_count_30d), round_amount_ratio=round(float(r.round_amount_ratio), 2), truth=int(r.label_role_misuse)) for r in top.itertuples()]
