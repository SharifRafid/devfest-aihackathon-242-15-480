"""
Feature engine for Second Thought.

Works on a full session or on any prefix of it (streaming), so the same code powers
offline training, the detection-latency metric, and the live per-event scorer.

Three signal families:
  structure  - which events appear, in which order, what is missing (telemetry, screens)
  timing     - inter-event gaps, typing speed, hesitation
  baseline   - how this session compares with THIS user's own history (hour, amounts, recipients, rhythm)
plus a Markov flow-likelihood trained on human sessions only (unsupervised anomaly signal).

Persona, gender, age, region and device class are deliberately NOT features.
"""
from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

TELEMETRY = {"a_ping", "a_offers", "a_heartbeat"}
MONEY_API = {"a_transfer", "a_cashout", "a_recharge", "a_billpay", "a_merchantpay"}
TYPING = {"s_recipient": 11, "s_amount": 4, "s_pin": 5, "s_otp": 6, "s_pinchange": 10}
DAILY_CAP = 25_000.0
START = "<s>"

FEATURE_NAMES = [
    "n_events", "n_screens", "n_api", "screen_ratio", "telemetry_count", "telemetry_ratio", "no_telemetry",
    "n_money", "money_total", "money_max", "amount_frac_cap", "new_recipient_count", "frac_new_recipient",
    "pin_errors", "has_pinchange", "has_add_beneficiary", "has_otp", "has_help", "has_balance_check",
    "money_without_pin_screen", "login_without_screen", "api_only_prefix",
    "dt_mean", "dt_std", "dt_cv", "dt_min", "dt_median", "frac_dt_lt_300", "frac_dt_lt_1000", "duration_s",
    "ms_per_char_min", "ms_per_char_mean", "impossible_typing", "money_per_minute", "hesitation_ratio",
    "mk_mean_nll", "mk_min_logp", "mk_n_unseen",
    "hour", "is_night", "new_device", "device_user_count", "hour_dev", "amount_z", "recipient_known_ratio",
    "n_prior_sessions", "rhythm_ratio",
]


# ---------------------------------------------------------------- Markov flow model
class MarkovFlow:
    """First-order transition model over event names, trained on human sessions only."""

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha; self.logp: dict = {}; self.vocab: set = set(); self.row_tot: dict = {}

    def fit(self, sequences):
        cnt = defaultdict(lambda: defaultdict(int))
        for seq in sequences:
            prev = START
            for e in seq:
                cnt[prev][e] += 1; prev = e
            self.vocab.add(prev)
        self.vocab |= {e for s in sequences for e in s} | {START}
        V = len(self.vocab)
        for a, row in cnt.items():
            tot = sum(row.values()); self.row_tot[a] = tot
            self.logp[a] = {b: math.log((c + self.alpha) / (tot + self.alpha * V)) for b, c in row.items()}
        self._V = V
        return self

    def lp(self, a, b):
        tot = self.row_tot.get(a, 0)
        return self.logp.get(a, {}).get(b, math.log(self.alpha / (tot + self.alpha * self._V)))

    def score(self, seq):
        """returns (mean negative log-lik, min logp, count of unseen transitions)"""
        if not seq: return 0.0, 0.0, 0
        prev, lps, unseen = START, [], 0
        for e in seq:
            l = self.lp(prev, e); lps.append(l)
            if e not in self.logp.get(prev, {}): unseen += 1
            prev = e
        return float(-np.mean(lps)), float(min(lps)), unseen

    def to_dict(self):
        return {"alpha": self.alpha, "vocab": sorted(self.vocab), "row_tot": self.row_tot,
                "logp": {a: dict(r) for a, r in self.logp.items()}}

    @classmethod
    def from_dict(cls, d):
        m = cls(d["alpha"]); m.vocab = set(d["vocab"]); m.row_tot = d["row_tot"]; m.logp = d["logp"]; m._V = len(m.vocab)
        return m


# ---------------------------------------------------------------- user history profile
@dataclass
class UserProfile:
    n_sessions: int = 0
    hour_sin: float = 0.0; hour_cos: float = 0.0         # running sums for circular mean
    log_amt_sum: float = 0.0; log_amt_sq: float = 0.0; n_amt: int = 0
    recipients: set = field(default_factory=set)
    confirm_dwell: list = field(default_factory=list)   # last 20 dwell values on s_amount+s_confirm
    dt_median: list = field(default_factory=list)       # last 20 session median gaps

    def usual_hour(self):
        if self.n_sessions == 0: return None
        return (math.degrees(math.atan2(self.hour_sin, self.hour_cos)) % 360) / 15.0

    def amount_stats(self):
        if self.n_amt < 2: return None, None
        m = self.log_amt_sum / self.n_amt
        v = max(self.log_amt_sq / self.n_amt - m * m, 0.05)
        return m, math.sqrt(v)

    def update(self, sess_hour, amounts, recipients, confirm_dwell, dt_med):
        self.n_sessions += 1
        self.hour_sin += math.sin(math.radians(sess_hour * 15)); self.hour_cos += math.cos(math.radians(sess_hour * 15))
        for a in amounts:
            if a > 0: la = math.log(a); self.log_amt_sum += la; self.log_amt_sq += la * la; self.n_amt += 1
        self.recipients |= set(r for r in recipients if r)
        if confirm_dwell: self.confirm_dwell = (self.confirm_dwell + [confirm_dwell])[-20:]
        if dt_med: self.dt_median = (self.dt_median + [dt_med])[-20:]

    def to_dict(self):
        return dict(n_sessions=self.n_sessions, hour_sin=self.hour_sin, hour_cos=self.hour_cos, log_amt_sum=self.log_amt_sum,
                    log_amt_sq=self.log_amt_sq, n_amt=self.n_amt, recipients=sorted(self.recipients),
                    confirm_dwell=self.confirm_dwell, dt_median=self.dt_median)

    @classmethod
    def from_dict(cls, d):
        p = cls(**{k: v for k, v in d.items() if k != "recipients"}); p.recipients = set(d["recipients"]); return p


def circ_hour_dist(a, b):
    d = abs(a - b) % 24
    return min(d, 24 - d)


# ---------------------------------------------------------------- session features
def session_features(events: list[dict], profile: UserProfile, markov: MarkovFlow,
                     device_user_count: int = 1, new_device: int = 0) -> dict:
    """events: list of dicts with keys event, dt_ms, amount, recipient_id, pin_error, ok, ts. Any prefix works."""
    n = len(events)
    if n == 0: return {k: 0.0 for k in FEATURE_NAMES}
    names = [e["event"] for e in events]
    dts = np.array([e["dt_ms"] for e in events[1:]], dtype=float) if n > 1 else np.array([0.0])
    screens = [x for x in names if x.startswith("s_")]
    apis = [x for x in names if x.startswith("a_")]
    tel = sum(1 for x in names if x in TELEMETRY)
    money_ev = [e for e in events if e["event"] in MONEY_API and e.get("ok", 1)]
    amounts = [float(e.get("amount", 0) or 0) for e in money_ev]
    recips = [e.get("recipient_id", "") for e in money_ev if e.get("recipient_id")]
    known = sum(1 for r in recips if r in profile.recipients)
    new_rec = len(recips) - known

    # path skips
    mwps = 0
    for i, e in enumerate(events):
        if e["event"] in MONEY_API and "s_pin" not in names[max(0, i - 3):i]: mwps += 1
    lws = int("a_login" in names and "s_login" not in names)
    api_only_prefix = int(all(x.startswith("a_") for x in names))

    # typing speed
    mpc = []
    for e in events:
        if e["event"] in TYPING and e["dt_ms"] > 0:
            mpc.append(e["dt_ms"] / TYPING[e["event"]])
    confirm_dwell = sum(e["dt_ms"] for e in events if e["event"] in ("s_confirm", "s_amount"))

    duration_s = max((events[-1]["ts"] - events[0]["ts"]) / 1000.0, 0.001)
    first_hour = ((events[0]["ts"] // 1000) % 86400) / 3600.0

    mk_nll, mk_min, mk_unseen = markov.score(names)

    uh = profile.usual_hour()
    hour_dev = circ_hour_dist(first_hour, uh) if uh is not None else 0.0
    am, asd = profile.amount_stats()
    amount_z = ((math.log(max(amounts)) - am) / asd) if (amounts and am is not None) else 0.0
    base_dwell = float(np.median(profile.confirm_dwell)) if profile.confirm_dwell else None
    hes = (confirm_dwell / base_dwell) if (base_dwell and confirm_dwell > 0) else 1.0
    base_dt = float(np.median(profile.dt_median)) if profile.dt_median else None
    rhythm = (float(np.median(dts)) / base_dt) if (base_dt and n > 1) else 1.0

    dt_mean = float(dts.mean()); dt_std = float(dts.std())
    f = dict(
        n_events=n, n_screens=len(screens), n_api=len(apis), screen_ratio=len(screens) / n,
        telemetry_count=tel, telemetry_ratio=tel / max(len(apis), 1), no_telemetry=int(tel == 0 and len(apis) >= 2),
        n_money=len(money_ev), money_total=sum(amounts), money_max=max(amounts) if amounts else 0.0,
        amount_frac_cap=(max(amounts) / DAILY_CAP) if amounts else 0.0,
        new_recipient_count=new_rec, frac_new_recipient=(new_rec / len(recips)) if recips else 0.0,
        pin_errors=sum(int(e.get("pin_error", 0)) for e in events),
        has_pinchange=int("a_pinchange" in names), has_add_beneficiary=int("a_add_beneficiary" in names),
        has_otp=int("a_otp" in names), has_help=int("s_help" in names), has_balance_check=int("s_balance" in names),
        money_without_pin_screen=mwps, login_without_screen=lws, api_only_prefix=api_only_prefix,
        dt_mean=dt_mean, dt_std=dt_std, dt_cv=dt_std / max(dt_mean, 1.0), dt_min=float(dts.min()), dt_median=float(np.median(dts)),
        frac_dt_lt_300=float((dts < 300).mean()), frac_dt_lt_1000=float((dts < 1000).mean()), duration_s=duration_s,
        ms_per_char_min=min(mpc) if mpc else 0.0, ms_per_char_mean=float(np.mean(mpc)) if mpc else 0.0,
        impossible_typing=sum(1 for v in mpc if v < 60), money_per_minute=len(money_ev) / (duration_s / 60.0),
        hesitation_ratio=min(hes, 20.0),
        mk_mean_nll=mk_nll, mk_min_logp=mk_min, mk_n_unseen=mk_unseen,
        hour=first_hour, is_night=int(first_hour < 5), new_device=int(new_device), device_user_count=device_user_count,
        hour_dev=hour_dev, amount_z=float(np.clip(amount_z, -6, 6)), recipient_known_ratio=(known / len(recips)) if recips else 1.0,
        n_prior_sessions=profile.n_sessions, rhythm_ratio=min(rhythm, 20.0),
    )
    return {k: float(f[k]) for k in FEATURE_NAMES}


def session_summary_for_profile(events: list[dict]):
    names = [e["event"] for e in events]
    money_ev = [e for e in events if e["event"] in MONEY_API and e.get("ok", 1)]
    hour = ((events[0]["ts"] // 1000) % 86400) / 3600.0
    dts = [e["dt_ms"] for e in events[1:]]
    return dict(sess_hour=hour, amounts=[float(e.get("amount", 0) or 0) for e in money_ev],
                recipients=[e.get("recipient_id", "") for e in money_ev],
                confirm_dwell=sum(e["dt_ms"] for e in events if e["event"] in ("s_confirm", "s_amount")) or None,
                dt_med=float(np.median(dts)) if dts else None)


# ---------------------------------------------------------------- dataset builder
def build_dataset(events: pd.DataFrame, sessions: pd.DataFrame, markov: MarkovFlow, device_counts: dict,
                  known_devices: dict | None = None, progress: bool = False):
    """Walk every user's sessions chronologically, scoring each against the profile built from its past.
    Returns (X DataFrame indexed by session_id, profiles dict user_id -> UserProfile at end of data)."""
    cols = ["event", "dt_ms", "amount", "recipient_id", "pin_error", "ok", "ts", "session_id"]
    ev_sorted = events.sort_values(["session_id", "idx"])
    grouped = {sid: g[cols].to_dict("records") for sid, g in ev_sorted.groupby("session_id", sort=False)}
    rows, profiles = [], {}
    sess_sorted = sessions.sort_values(["user_id", "start_ts"])
    seen_devices: dict[str, set] = defaultdict(set)
    for i, s in enumerate(sess_sorted.itertuples(index=False)):
        prof = profiles.setdefault(s.user_id, UserProfile())
        evs = grouped[s.session_id]
        nd = int(s.device_id not in seen_devices[s.user_id]) if seen_devices[s.user_id] else 0
        f = session_features(evs, prof, markov, device_user_count=device_counts.get(s.device_id, 1), new_device=nd)
        f["session_id"] = s.session_id; rows.append(f)
        prof.update(**session_summary_for_profile(evs)); seen_devices[s.user_id].add(s.device_id)
        if progress and i % 5000 == 0: print(f"  featurized {i:,}/{len(sess_sorted):,}")
    X = pd.DataFrame(rows).set_index("session_id")
    return X, profiles
