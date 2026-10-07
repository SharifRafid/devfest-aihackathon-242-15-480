# Second Thought — Session Authenticity Engine for MFS
### AI Hackathon 2026 (DIU CPC × upay) · Track 01 Trust & Risk Intelligence (Account Takeover + Scam Intelligence)

Clock: plan written 09:25 on 2026-10-07. Hard stop ≈ 13:00. No extensions (rule 6.2).

---

## 1. The problem (in the PDF's required template)

> For upay customers, especially first-time and low-literacy users, account takeover and coerced transactions executed through reverse-engineered app APIs cause direct financial loss and loss of trust, even though the app already enforces obfuscation, OTP auto-fill, VPN and integrity checks. We will build **Second Thought**, an AI session-authenticity engine that uses the clickstream upay already collects (API calls, screen visits, inter-event timing, device context) to decide in real time whether a session behaves like the genuine human owner, and to trigger graduated interventions (explain-and-confirm, step-up verification, hold for review). Success is measured by **% of fraudulent sessions stopped before the first money-moving call**, at a **false-friction rate on genuine sessions under 2%**.

Why this is different from what everyone else will build: fraud models score *transactions*. Second Thought scores the *path to the transaction*. By the time a transaction model sees the transfer, the attacker has already won the session. Flow and timing are available 5–10 events earlier.

Why AI is material (not a rule): there is no single rule for "this doesn't look like a human using the app." It is the joint distribution of transition order, dwell times, telemetry completeness, typing speed, and *this user's own history*. Attackers who mimic one feature break another.

## 2. Threat model (each becomes a synthetic attack archetype)

| # | Archetype | What the session looks like | Primary signal |
|---|---|---|---|
| A1 | **Scripted ATO via reverse-engineered API** | Login → send-money directly; no home/balance/screen-view events; uniform 100–300 ms gaps; missing analytics pings the real app fires | Path skips, missing telemetry, timing uniformity |
| A2 | **OTP-relay / SIM-swap takeover** | New device, PIN reset, add beneficiary, max-amount transfer, all within 90 s | New-device + velocity + user-baseline deviation |
| A3 | **Coerced victim ("fake upay office" call)** | Genuine device and human timing, but first-ever recipient, amount near daily cap, odd hour, repeated PIN errors, long hesitation then rapid completion | User-baseline deviation + hesitation profile → **Second Thought screen** |
| A4 | **Personal wallet used as merchant/agent** | Account-level: dozens of unique inbound senders/day, round amounts, periodic bulk cash-out, inbound:outbound counterparty ratio | 30-day account-role features |
| A5 | **Gambling / fake-purchase laundering** | Repeated night-time merchant payments to a small set of newly registered merchants, chain to cash-out | Counterparty novelty + temporal pattern |
| A6 | **Emulator / bot farm** | Many accounts, identical timing signature and device fingerprint, mass onboarding | Cross-account timing-signature similarity |
| A7 | **Adaptive attacker** (A1 with jittered human-like timing) | Same as A1 but log-normal random delays | Shows degradation honestly; still caught by path skips + telemetry gaps + user baseline. *This is the slide that wins technical Q&A.* |

Hold A5 (or A7) entirely out of training to prove the unsupervised layer catches **novel** attacks.

## 3. Data: synthetic clickstream generator (no production data, PDF §11)

- **App graph**: ~22 nodes (splash, login, otp, home, balance, send_money, recipient_entry, amount_entry, pin_entry, confirm, success, cash_out, recharge, bill_pay, merchant_qr, add_money, statement, profile, pin_change, add_beneficiary, help, logout) + background telemetry events (`analytics_ping`, `prefetch_offers`, `heartbeat`) that the genuine app always fires.
- **Human generator**: Markov transitions per persona (student, salaried, RMG worker, small merchant, elderly/low-literacy, rural feature-phone/USSD). Dwell times log-normal per screen; typing speed per persona (elderly = slow, student = fast); back-navigation and hesitation; usual hours, usual recipients, usual amounts, 1–2 devices.
- **Attack injector**: archetypes A1–A7 with configurable prevalence (~3% of sessions overall, class-imbalanced like reality).
- **Scale**: 3,000 users × 30 days ≈ 60k sessions ≈ 800k events. 20% holdout by *user* (not by session) so per-user baselines don't leak.
- `data/ASSUMPTIONS.md` documents every distribution and injected pattern.

## 4. Models (layered, each explainable)

| Layer | Method | Output | Why |
|---|---|---|---|
| L1 Flow likelihood | Markov transition model trained on **human-only** sessions → per-session log-likelihood + per-transition surprise | unsupervised anomaly score | Catches novel attacks; no labels needed |
| L2 Session classifier | LightGBM on ~40 engineered session features: timing CV, min gap, impossible-speed step count, path-skip count, telemetry-completeness ratio, out-of-order calls, PIN error count, new-device flag, hour-of-day deviation, recipient novelty, amount z-score vs user, hesitation-before-commit… | P(not authentic), SHAP top-3 | Supervised precision; explainability |
| L3 User baseline deviation | Per-user profile (hours, recipients, amounts, devices, typical path) → Mahalanobis-style deviation | deviation score | Separates "weird for everyone" from "weird for *this* user" (A3 lives here) |
| L4 Account-role misuse | LightGBM on 30-day account features | P(personal wallet acting as merchant/agent) | A4; separate problem, separate model |
| L5 Isolation Forest on L2 features | unsupervised | second opinion | ensemble robustness, novel-attack test |
| Optional L6 | small GRU sequence model on event ids + Δt | sequence score | "AI depth" talking point; **cut first if behind** |

**Policy layer (business rules, kept separate from ML per PDF §12):**
score < 0.3 → allow · 0.3–0.6 → **Second Thought** screen (plain Bangla/English explanation + confirm + 30 s cooling) · 0.6–0.85 → step-up (re-auth / call-back) · > 0.85 → hold funds + analyst queue. **Never** autonomous permanent block (PDF §14). Analyst console shows SHAP + rule trace + LLM narrative grounded only in the structured evidence JSON.

**Streaming design**: features update incrementally per event; score recomputed per event; we report **detection latency** = event index at which score crosses threshold vs event index of first money-moving call.

## 5. Evaluation (what goes in `models/metrics.json` and on the slide)

1. AUC / PR-AUC overall and **per archetype** on user-level holdout.
2. **% stopped before money moved** (the headline metric) and median events-to-detection.
3. False-friction rate on genuine sessions, overall **and sliced by persona** (elderly/low-literacy and feature-phone users must *not* be flagged for being slow — fairness, PDF §14).
4. **Novel-attack test**: train without A5, report recall on A5 from L1+L5 alone.
5. **Adaptive-attacker test**: A7 recall, and which features still fire.
6. Baseline comparison: simple velocity/new-device rule vs our model (answers "isn't this just rules?").
7. Impact: on the synthetic month, ৳ fraud loss prevented, friction cost, analyst minutes saved; extrapolate per 1M users with stated assumptions.

## 6. Demo (what the judges see, ~3 minutes)

1. **Session Replay Theatre**: three sessions play side-by-side as event timelines (genuine · scripted ATO · coerced victim). A live score bar updates per event; at the threshold, the intervention fires. Judges watch the attacker get caught at event 4 of 9, before `POST /transfer`.
2. **Phone frame**: the customer-facing **Second Thought** screen (Bangla + English): "আপনি এই নম্বরে আগে কখনো টাকা পাঠাননি… / You've never sent money to this number before, and it's 2:40 AM. Did someone ask you to do this over the phone?" Confirm / Cancel / "I was asked by a caller" → routes to hold + call-back.
3. **Analyst console**: alert queue, SHAP reasons, LLM investigation summary, one-click actions (release / step-up / freeze-for-review).
4. **"Attack me" button**: runs a scripted client against our own FastAPI and shows it being caught live. Highest-impact 20 seconds of the demo.

## 7. Architecture

```
upay app / existing step-tracker ──events──▶ Ingest API (FastAPI /events)
                                                 │
                                  Streaming feature engine (per-session window + per-user profile store)
                                                 │
                 ┌──────────────┬────────────────┼──────────────┬──────────────┐
            L1 Markov      L2 LightGBM     L3 user baseline   L4 account role   L5 IsoForest
                 └──────────────┴────────────────┼──────────────┴──────────────┘
                                          Ensemble score + SHAP
                                                 │
                                  Policy engine (rules, thresholds, human-oversight)
                                     │                     │                  │
                              allow        Second Thought screen       analyst queue + LLM narrative
                                                 │
                                   Feedback loop (analyst label → retrain)
```
Integration story: it is a **sidecar on telemetry upay already emits**. Zero app changes to start; the policy layer becomes an API the app calls before `confirm`. Stateless scoring, O(1) feature updates per event, horizontally scalable.

Stack: Python · pandas · scikit-learn · LightGBM · SHAP · FastAPI · Vite + React + Tailwind · Anthropic API for the analyst narrative (templated fallback, prompt-injection guard: the LLM never sees free text from the user, only our JSON).

## 8. Schedule (≈ 3 h 35 m from 09:25)

| Window | Deliverable | Done when |
|---|---|---|
| 09:25–09:35 | README problem statement + 9-step logic chain; **ask organizers the submission format** | README committed |
| 09:35–10:10 | `data/generate.py`: app graph, personas, A1–A7 injector, user-level holdout, `ASSUMPTIONS.md` | CSV/parquet of events + session labels; quick sanity stats |
| 10:10–11:00 | `ml/features.py`, `ml/train.py`: L1–L5, metrics incl. per-archetype, latency, fairness, novel-attack, adaptive-attacker, rule baseline; SHAP | `metrics.json` + plots |
| 11:00–11:30 | `api/`: `/events` streaming scorer, `/sessions/{id}/score`, `/explain`, policy engine, LLM narrative w/ fallback | curl demo of a scripted attack getting caught |
| 11:30–12:20 | `web/`: Replay Theatre + phone Second Thought screen + analyst console + "Attack me" | Click-through, no console errors |
| 12:20–12:40 | README metrics + impact, architecture diagram, 6-slide deck | Deck PDF in repo |
| 12:40–12:50 | 2-min screen recording (insurance for live-demo failure) | Video linked |
| 12:50–13:00 | Buffer, submission checklist, final `/push`, open repo link in incognito | Submitted |

**Cut order if behind**: L6 GRU → account-role model (A4) → LLM analyst narrative → Bangla toggle → analyst console. **Never cut**: generator, L1+L2, latency metric, Replay Theatre, phone screen, README metrics.

## 9. Judges' Q&A — prepared answers

- *"Attackers will just add random delays."* → Show A7. Timing is one of five signal families; path skips, telemetry completeness, device, and per-user baseline survive. Defence in depth, continuous retraining from analyst labels.
- *"Isn't this just velocity rules?"* → Rule baseline vs model table on holdout; rules miss A3 (coerced victim) entirely because the victim *is* the human.
- *"Won't slow elderly users get flagged?"* → Fairness slice table; L3 compares the user to *themselves*, so slow is normal for a slow user.
- *"Privacy?"* → Behavioral metadata only (endpoint, timing, screen id); no message content, no PII in features; stays inside upay.
- *"What changes with real data?"* → Event schema maps 1:1 to the existing step-tracker; recalibrate thresholds on real base rates; shadow-mode for 2 weeks, then A/B the friction screen; analyst feedback loop closes the retraining cycle.
- *"Why not a transformer?"* → Latency and explainability at the point of intervention; GRU is the optional L6, the roadmap item.

## 10. Rules compliance checklist
- Own AI account only (5.3). Prompt history in `PROMPT.md` + commit messages (5.6, 7.4).
- Synthetic data only, assumptions documented, holdout never trained on (§11).
- No autonomous consequential decisions; human review tier (§14).
- Submission format confirmed with organizers (8.2) — **TODO ask now**.

## 11. Workflow tooling
`PROMPT.md` auto-logs every prompt (hook). `/push` commits+pushes with files + prompts. `/autopush status|stop|start N` controls the 15-min loop (running).
