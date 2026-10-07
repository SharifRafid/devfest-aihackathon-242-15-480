"""
Second Thought — synthetic MFS clickstream generator.

Produces:
  data/out/events.parquet    one row per app event (screen view or API call)
  data/out/sessions.parquet  one row per session with ground-truth label
  data/out/accounts.parquet  30-day account-level aggregates (for account-role misuse)
  data/out/users.parquet     user profiles (persona, usual hour, devices, frequent recipients)

Everything is synthetic. See data/ASSUMPTIONS.md for every distribution and injected pattern.
Deterministic under --seed.
"""
from __future__ import annotations
import argparse, math, random, uuid
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "out"
DAILY_CAP = 25_000  # BDT send-money daily cap assumption

# ---------------------------------------------------------------- vocabulary
# screens (s_*) are rendered by the genuine app; api (a_*) are backend calls.
TELEMETRY = {"a_ping", "a_offers", "a_heartbeat"}
MONEY_API = {"a_transfer", "a_cashout", "a_recharge", "a_billpay", "a_merchantpay"}
TYPING_SCREENS = {"s_recipient": 11, "s_amount": 4, "s_pin": 5, "s_otp": 6, "s_pinchange": 10}

# ---------------------------------------------------------------- personas
@dataclass
class Persona:
    name: str
    weight: float
    dwell_mult: float          # multiplier on base screen dwell
    ms_per_char: float         # typing speed
    pin_err_p: float
    back_p: float
    hours: tuple              # (mean_hour, sd_hour) usual activity window
    amount_mu: float           # lognormal mean (log BDT)
    amount_sigma: float
    n_recipients: tuple        # (min,max) frequent recipients
    sessions_per_day: float
    intents: dict = field(default_factory=dict)
    devices: tuple = (1, 2)
    feature_phone_p: float = 0.0

PERSONAS = [
    Persona("student",      0.22, 0.75, 180, 0.04, 0.12, (20, 3.0), 6.3, 0.6, (3, 6), 0.9,
            {"send": .30, "recharge": .30, "merchant": .20, "balance": .10, "bill": .03, "cashout": .05, "addmoney": .02}),
    Persona("salaried",     0.25, 1.00, 230, 0.05, 0.10, (19, 3.5), 7.4, 0.7, (4, 8), 0.7,
            {"send": .30, "bill": .20, "merchant": .15, "recharge": .10, "balance": .10, "cashout": .10, "addmoney": .05}),
    Persona("rmg_worker",   0.18, 1.25, 320, 0.08, 0.14, (20, 2.5), 7.2, 0.8, (2, 4), 0.4,
            {"send": .45, "cashout": .25, "recharge": .15, "balance": .10, "bill": .03, "merchant": .02}),
    Persona("small_merchant",0.12, 1.00, 240, 0.05, 0.08, (14, 5.0), 7.0, 0.9, (5, 10), 1.6,
            {"balance": .25, "cashout": .25, "send": .20, "statement": .10, "addmoney": .10, "recharge": .05, "bill": .05}),
    Persona("elderly",      0.10, 1.90, 520, 0.14, 0.22, (11, 3.0), 7.0, 0.6, (1, 3), 0.3,
            {"balance": .35, "send": .25, "cashout": .25, "recharge": .10, "bill": .05}),
    Persona("rural_lowlit", 0.13, 1.60, 450, 0.12, 0.20, (12, 4.0), 6.8, 0.7, (1, 3), 0.35,
            {"balance": .30, "cashout": .35, "send": .20, "recharge": .15}, devices=(1, 1), feature_phone_p=0.5),
]
PW = np.array([p.weight for p in PERSONAS]); PW = PW / PW.sum()

# base dwell (ms) per screen, lognormal sigma
BASE_DWELL = {
    "s_splash": (1200, .3), "s_login": (2500, .4), "s_otp": (6000, .4), "s_home": (4000, .6),
    "s_balance": (3500, .5), "s_send": (2500, .5), "s_recipient": (5000, .4), "s_amount": (4500, .5),
    "s_pin": (3500, .4), "s_confirm": (3500, .6), "s_success": (2500, .5), "s_cashout": (3000, .5),
    "s_recharge": (4000, .5), "s_bill": (6000, .5), "s_qr": (3000, .5), "s_addmoney": (5000, .5),
    "s_statement": (8000, .7), "s_profile": (4000, .6), "s_help": (9000, .7), "s_pinchange": (9000, .4),
    "s_beneficiary": (7000, .4),
}
API_LAT = (350, .45)  # api round-trip ms lognormal


def ln(rng, mu_ms, sigma):
    return float(rng.lognormal(math.log(mu_ms), sigma))


# ---------------------------------------------------------------- users
def make_users(rng: np.random.Generator, n_users: int):
    users = []
    pool_recipients = [f"R{i:06d}" for i in range(n_users * 3)]
    for i in range(n_users):
        p = PERSONAS[rng.choice(len(PERSONAS), p=PW)]
        n_dev = int(rng.integers(p.devices[0], p.devices[1] + 1))
        nrec = int(rng.integers(p.n_recipients[0], p.n_recipients[1] + 1))
        users.append(dict(
            user_id=f"U{i:05d}", persona=p.name,
            usual_hour=float(np.clip(rng.normal(p.hours[0], 1.0), 6, 23)), hour_sd=p.hours[1],
            devices=[f"D{uuid.uuid4().hex[:8]}" for _ in range(n_dev)],
            recipients=list(rng.choice(pool_recipients, nrec, replace=False)),
            amount_mu=p.amount_mu + rng.normal(0, .25), amount_sigma=p.amount_sigma,
            speed_mult=float(np.clip(rng.normal(1.0, .15), .6, 1.6)),
            feature_phone=bool(rng.random() < p.feature_phone_p),
            region=rng.choice(["dhaka", "chattogram", "rural_north", "rural_south"], p=[.4, .2, .2, .2]),
            gender=rng.choice(["F", "M"], p=[.42, .58]),
            age=int(np.clip(rng.normal(55 if p.name == "elderly" else 30, 8), 18, 80)),
        ))
    return users, pool_recipients


# ---------------------------------------------------------------- session builder
class SessionBuilder:
    def __init__(self, rng, user, start_ts, device, label, archetype, persona):
        self.rng, self.u, self.t, self.dev = rng, user, start_ts, device
        self.label, self.arch, self.p = label, archetype, persona
        self.events = []
        self.sid = f"S{uuid.uuid4().hex[:10]}"
        self.next_hb = start_ts + 30_000
        self.money = 0.0; self.pin_errors = 0; self.new_recips = 0; self.n_money = 0

    def ev(self, name, dt_ms, **kw):
        self.t += dt_ms
        row = dict(session_id=self.sid, user_id=self.u["user_id"], ts=int(self.t), event=name,
                   dt_ms=int(dt_ms), device_id=self.dev, amount=kw.get("amount", 0.0),
                   recipient_id=kw.get("recipient", ""), recipient_new=int(kw.get("recipient_new", 0)),
                   pin_error=int(kw.get("pin_error", 0)), ok=int(kw.get("ok", 1)))
        self.events.append(row)

    # --- genuine-app primitives (screens + their telemetry) ---
    def screen(self, name, mult=1.0, chars=None):
        base, sig = BASE_DWELL[name]
        d = ln(self.rng, base, sig) * self.p.dwell_mult * self.u["speed_mult"] * mult
        if chars:
            d += chars * self.p.ms_per_char * self.u["speed_mult"] * float(self.rng.lognormal(0, .25))
        self.ev(name, d)
        self.maybe_heartbeat()

    def api(self, name, lat_mult=1.0, **kw):
        self.ev(name, ln(self.rng, API_LAT[0], API_LAT[1]) * lat_mult, **kw)

    def maybe_heartbeat(self):
        if self.t >= self.next_hb:
            self.ev("a_heartbeat", 5); self.next_hb = self.t + 30_000

    def login(self, new_device):
        self.screen("s_splash"); self.api("a_ping")
        self.screen("s_login", chars=5); self.api("a_login")
        if new_device:
            self.screen("s_otp", chars=6); self.api("a_otp")
        self.screen("s_home"); self.api("a_balance"); self.api("a_offers"); self.api("a_ping")

    def send_money(self, recipient, recipient_new, amount, hesitation=1.0, forced_pin_err=None):
        self.screen("s_send")
        if self.rng.random() < self.p.back_p * .5: self.screen("s_home", .5); self.screen("s_send", .5)
        self.screen("s_recipient", chars=11)
        self.api("a_resolve_recipient", recipient=recipient, recipient_new=recipient_new)
        self.screen("s_amount", mult=hesitation, chars=len(str(int(amount))))
        self.screen("s_confirm", mult=hesitation)
        errs = forced_pin_err if forced_pin_err is not None else (self.rng.random() < self.p.pin_err_p)
        for _ in range(int(errs)):
            self.screen("s_pin", chars=5); self.api("a_transfer", ok=0, pin_error=1, amount=amount, recipient=recipient, recipient_new=recipient_new)
            self.pin_errors += 1
        self.screen("s_pin", chars=5)
        self.api("a_transfer", amount=amount, recipient=recipient, recipient_new=recipient_new, lat_mult=1.6)
        self.money += amount; self.n_money += 1; self.new_recips += recipient_new
        self.screen("s_success"); self.api("a_ping")

    def simple_money(self, screen, api, amount, recipient="", recipient_new=0):
        self.screen(screen, chars=6)
        self.screen("s_pin", chars=5)
        self.api(api, amount=amount, recipient=recipient, recipient_new=recipient_new, lat_mult=1.6)
        self.money += amount; self.n_money += 1; self.new_recips += recipient_new
        self.screen("s_success"); self.api("a_ping")

    def amount(self, frac_cap=None):
        if frac_cap is not None:
            return float(round(DAILY_CAP * frac_cap, -2))
        a = float(self.rng.lognormal(self.u["amount_mu"], self.u["amount_sigma"]))
        return float(min(max(round(a, -1), 20), DAILY_CAP))

    def recipient(self, force_new=False):
        if force_new or self.rng.random() < 0.08:
            return f"R{uuid.uuid4().hex[:6]}", 1
        return str(self.rng.choice(self.u["recipients"])), 0


# ---------------------------------------------------------------- human session
def human_session(rng, user, start_ts, persona, device, new_device):
    b = SessionBuilder(rng, user, start_ts, device, "human", "human", persona)
    b.login(new_device)
    intents = list(persona.intents.items()); names = [k for k, _ in intents]; w = np.array([v for _, v in intents]); w /= w.sum()
    n_actions = 1 + int(rng.random() < .35) + int(rng.random() < .1)
    if rng.random() < 0.55: b.screen("s_balance")
    for _ in range(n_actions):
        it = rng.choice(names, p=w)
        if it == "send":
            r, new = b.recipient(); b.send_money(r, new, b.amount())
        elif it == "cashout": b.simple_money("s_cashout", "a_cashout", b.amount())
        elif it == "recharge": b.simple_money("s_recharge", "a_recharge", float(rng.choice([20, 50, 100, 200, 500])))
        elif it == "bill": b.simple_money("s_bill", "a_billpay", b.amount())
        elif it == "merchant": b.simple_money("s_qr", "a_merchantpay", b.amount() * .4, recipient=f"M{rng.integers(0, 400):04d}")
        elif it == "addmoney": b.simple_money("s_addmoney", "a_addmoney", b.amount())
        elif it == "statement": b.screen("s_statement"); b.api("a_statement")
        elif it == "balance": b.screen("s_balance"); b.api("a_balance")
        if rng.random() < persona.back_p: b.screen("s_home", .6)
    if rng.random() < 0.4: b.api("a_logout")
    return b


# ---------------------------------------------------------------- attack archetypes
def a1_scripted(rng, user, start_ts, persona, device, adaptive=False):
    """Reverse-engineered API client. No screens, no telemetry. A7 = same with human-like jitter."""
    b = SessionBuilder(rng, user, start_ts, device, "fraud", "A7_adaptive_scripted" if adaptive else "A1_scripted_api", persona)
    gap = (lambda: ln(rng, 2500, .6)) if adaptive else (lambda: float(rng.uniform(90, 320)))
    b.ev("a_login", gap())
    if rng.random() < .3: b.ev("a_otp", gap())
    if rng.random() < .5: b.ev("a_balance", gap())
    for _ in range(int(rng.integers(1, 5))):
        r, new = f"R{uuid.uuid4().hex[:6]}", 1
        if rng.random() < .5: b.ev("a_resolve_recipient", gap(), recipient=r, recipient_new=1)
        amt = b.amount(frac_cap=float(rng.uniform(.3, 1.0)))
        b.ev("a_transfer", gap() + ln(rng, 400, .3), amount=amt, recipient=r, recipient_new=1)
        b.money += amt; b.n_money += 1; b.new_recips += 1
    return b


def a2_otp_relay(rng, user, start_ts, persona, device):
    """Takeover from a NEW device after OTP relay / SIM swap: pin change, add beneficiary, drain."""
    b = SessionBuilder(rng, user, start_ts, device, "fraud", "A2_otp_relay_takeover", persona)
    b.p = PERSONAS[0]  # attacker types fast regardless of victim persona
    b.login(new_device=True)
    b.screen("s_profile", .5); b.screen("s_pinchange", .6, chars=10); b.api("a_pinchange")
    b.screen("s_beneficiary", .6, chars=11); b.api("a_add_beneficiary", recipient_new=1)
    r = f"R{uuid.uuid4().hex[:6]}"
    b.send_money(r, 1, b.amount(frac_cap=float(rng.uniform(.8, 1.0))), hesitation=.5, forced_pin_err=0)
    if rng.random() < .5: b.simple_money("s_cashout", "a_cashout", b.amount(frac_cap=.5))
    return b


def a3_coerced(rng, user, start_ts, persona, device):
    """Genuine human on a scam call: own device, own rhythm, but first-ever recipient, near-cap amount, hesitation, PIN fumbles."""
    b = SessionBuilder(rng, user, start_ts, device, "fraud", "A3_coerced_victim", persona)
    b.login(new_device=False)
    if rng.random() < .4: b.screen("s_balance"); b.api("a_balance")
    if rng.random() < .25: b.screen("s_help", 1.5)
    r = f"R{uuid.uuid4().hex[:6]}"
    b.send_money(r, 1, b.amount(frac_cap=float(rng.uniform(.6, 1.0))), hesitation=float(rng.uniform(2.0, 4.0)),
                 forced_pin_err=int(rng.random() < .55) + int(rng.random() < .25))
    if rng.random() < .35:
        b.send_money(r, 0, b.amount(frac_cap=float(rng.uniform(.3, .6))), hesitation=1.5)
    return b


def a5_gambling(rng, user, start_ts, persona, device):
    """Night-time repeated merchant payments to a small set of new merchants, then cash-out."""
    b = SessionBuilder(rng, user, start_ts, device, "fraud", "A5_gambling_laundering", persona)
    b.p = PERSONAS[0]
    b.login(new_device=bool(rng.random() < .3))
    merchants = [f"MX{rng.integers(0, 30):03d}" for _ in range(2)]
    for _ in range(int(rng.integers(3, 7))):
        b.simple_money("s_qr", "a_merchantpay", float(rng.choice([500, 1000, 2000, 5000])), recipient=str(rng.choice(merchants)), recipient_new=1)
    if rng.random() < .5: b.simple_money("s_cashout", "a_cashout", b.amount(frac_cap=.4))
    return b


def a6_emulator(rng, user, start_ts, persona, device, farm_seed):
    """Emulator farm: many accounts share device ids and an identical, low-variance timing signature."""
    b = SessionBuilder(rng, user, start_ts, device, "fraud", "A6_emulator_farm", persona)
    frng = np.random.default_rng(farm_seed)
    sig = {k: float(frng.uniform(600, 1400)) for k in BASE_DWELL}  # farm-wide fixed dwell per screen
    def scr(name): b.ev(name, sig[name] * float(rng.normal(1, .03)))
    def api(name, **kw): b.ev(name, 180 * float(rng.normal(1, .05)), **kw)
    scr("s_splash"); api("a_ping"); scr("s_login"); api("a_login"); scr("s_home"); api("a_balance"); api("a_offers")
    scr("s_send"); scr("s_recipient"); r = f"R{uuid.uuid4().hex[:6]}"; api("a_resolve_recipient", recipient=r, recipient_new=1)
    scr("s_amount"); scr("s_confirm"); scr("s_pin"); amt = float(rng.choice([480, 490, 495, 500]))
    api("a_transfer", amount=amt, recipient=r, recipient_new=1); b.money += amt; b.n_money += 1; b.new_recips += 1
    scr("s_success")
    return b


# ---------------------------------------------------------------- main generation loop
def generate(n_users=3000, days=30, seed=7, prevalence=None):
    rng = np.random.default_rng(seed); random.seed(seed)
    prevalence = prevalence or dict(A1=.008, A2=.004, A3=.006, A5=.004, A6=.005, A7=.005)
    users, _ = make_users(rng, n_users)
    pmap = {p.name: p for p in PERSONAS}
    farm_devices = [f"EMU{uuid.uuid4().hex[:6]}" for _ in range(12)]
    t0 = pd.Timestamp("2026-09-01").value // 10**6
    all_events, sessions = [], []
    for u in users:
        p = pmap[u["persona"]]
        n_sess = rng.poisson(p.sessions_per_day * days)
        for _ in range(n_sess):
            day = int(rng.integers(0, days))
            hour = float(np.clip(rng.normal(u["usual_hour"], u["hour_sd"]), 0, 23.99))
            start = t0 + day * 86_400_000 + int(hour * 3_600_000)
            roll = rng.random(); acc = 0.0; arch = "human"
            for k, v in prevalence.items():
                acc += v
                if roll < acc: arch = k; break
            new_dev = rng.random() < .03
            device = str(rng.choice(u["devices"])) if not new_dev else f"D{uuid.uuid4().hex[:8]}"
            if arch == "human": b = human_session(rng, u, start, p, device, new_dev)
            elif arch == "A1":
                start = t0 + day * 86_400_000 + int(rng.uniform(0, 24) * 3_600_000)
                b = a1_scripted(rng, u, start, p, f"D{uuid.uuid4().hex[:8]}" if rng.random() < .8 else device)
            elif arch == "A7":
                start = t0 + day * 86_400_000 + int(rng.uniform(0, 24) * 3_600_000)
                b = a1_scripted(rng, u, start, p, f"D{uuid.uuid4().hex[:8]}" if rng.random() < .8 else device, adaptive=True)
            elif arch == "A2": b = a2_otp_relay(rng, u, start + int(rng.uniform(-6, 6) * 3_600_000), p, f"D{uuid.uuid4().hex[:8]}")
            elif arch == "A3":
                # scam calls cluster in daytime/evening working hours of the scammer, sometimes night
                start = t0 + day * 86_400_000 + int((rng.uniform(10, 23) if rng.random() < .7 else rng.uniform(0, 5)) * 3_600_000)
                b = a3_coerced(rng, u, start, p, device)
            elif arch == "A5":
                start = t0 + day * 86_400_000 + int(rng.uniform(22, 29) % 24 * 3_600_000)
                b = a5_gambling(rng, u, start, p, device)
            elif arch == "A6": b = a6_emulator(rng, u, start, p, str(rng.choice(farm_devices)), farm_seed=seed)
            evs = b.events
            first_money = next((i for i, e in enumerate(evs) if e["event"] in MONEY_API and e["ok"]), -1)
            sessions.append(dict(
                session_id=b.sid, user_id=u["user_id"], persona=u["persona"], region=u["region"], gender=u["gender"],
                age=u["age"], feature_phone=u["feature_phone"], device_id=b.dev,
                new_device=int(b.dev not in u["devices"]), start_ts=int(evs[0]["ts"]), hour=hour if arch == "human" else ((evs[0]["ts"] - t0) % 86_400_000) / 3_600_000,
                n_events=len(evs), label=b.label, archetype=b.arch, money_total=b.money, n_money=b.n_money,
                new_recipients=b.new_recips, pin_errors=b.pin_errors, first_money_idx=first_money,
            ))
            all_events.extend(evs)
    ev = pd.DataFrame(all_events); se = pd.DataFrame(sessions)
    ev["idx"] = ev.groupby("session_id").cumcount()
    # user-level holdout split (no per-user leakage)
    uids = np.array([u["user_id"] for u in users]); rng.shuffle(uids)
    test_users = set(uids[: int(.2 * len(uids))])
    se["split"] = np.where(se.user_id.isin(test_users), "test", "train")
    ev = ev.merge(se[["session_id", "split", "label", "archetype"]], on="session_id")
    us = pd.DataFrame(users); us["devices"] = us.devices.apply(list); us["recipients"] = us.recipients.apply(list)
    us["split"] = np.where(us.user_id.isin(test_users), "test", "train")
    acc = make_accounts(rng, us, se)
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_parquet(OUT / "events.parquet", index=False); se.to_parquet(OUT / "sessions.parquet", index=False)
    us.to_parquet(OUT / "users.parquet", index=False); acc.to_parquet(OUT / "accounts.parquet", index=False)
    return ev, se, us, acc


def make_accounts(rng, users: pd.DataFrame, sessions: pd.DataFrame):
    """30-day account-level aggregates. A4 = personal wallet behaving like a merchant/agent (2% of users)."""
    g = sessions[sessions.label == "human"].groupby("user_id").agg(outbound_tx=("n_money", "sum"), out_amt=("money_total", "sum")).reindex(users.user_id).fillna(0)
    rows = []
    for _, u in users.iterrows():
        misuse = rng.random() < .02 and u.persona in ("salaried", "student", "rural_lowlit", "rmg_worker")
        out_tx = float(g.loc[u.user_id, "outbound_tx"])
        if misuse:
            inbound = int(rng.integers(150, 600)); senders = int(inbound * rng.uniform(.6, .95))
            cashouts = int(rng.integers(20, 45)); round_ratio = float(rng.uniform(.6, .9)); night = float(rng.uniform(.15, .4))
            med_in = float(rng.choice([100, 150, 200, 300, 500])); out_tx += cashouts
        else:
            inbound = int(rng.poisson({"small_merchant": 60, "salaried": 6, "student": 5, "rmg_worker": 4, "elderly": 3, "rural_lowlit": 4}[u.persona]))
            senders = int(min(inbound, rng.integers(1, 6) if u.persona != "small_merchant" else rng.integers(20, 50)))
            cashouts = int(rng.poisson(3 if u.persona != "small_merchant" else 10)); round_ratio = float(rng.uniform(.1, .4)); night = float(rng.uniform(0, .12))
            med_in = float(rng.lognormal(7.0, .6))
        rows.append(dict(user_id=u.user_id, persona=u.persona, split=u.split, is_registered_merchant=int(u.persona == "small_merchant"),
                         inbound_tx_30d=inbound, unique_senders_30d=senders, outbound_tx_30d=int(out_tx),
                         cashout_count_30d=cashouts, round_amount_ratio=round_ratio, night_ratio=night,
                         median_inbound_amt=med_in, sender_concentration=senders / max(inbound, 1),
                         cashout_to_inbound=cashouts / max(inbound, 1), label_role_misuse=int(misuse)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--users", type=int, default=3000); ap.add_argument("--days", type=int, default=30); ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    ev, se, us, acc = generate(a.users, a.days, a.seed)
    print(f"events={len(ev):,} sessions={len(se):,} users={len(us):,}")
    print(se.archetype.value_counts().to_string())
    print(se.groupby("split").size().to_string())
    print("accounts misuse:", acc.label_role_misuse.sum())
