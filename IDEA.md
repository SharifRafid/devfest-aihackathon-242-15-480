# Second Thought — Idea Submission

**Track 01 · Trust & Risk Intelligence** (account takeover + scam intelligence)
**Team:** solo · **Event:** AI Hackathon 2026, DIU CPC × upay · **Date:** 2026-10-07

> Every fraud model scores the transaction. **Second Thought scores the path to it.**

**Live demo:** https://secondthought.dubd.site (mirror: https://second-thought-pink.vercel.app) · **Repo:** https://github.com/SharifRafid/devfest-aihackathon-242-15-480 · **Deck:** `deck/SecondThought-deck.pdf`

---

## 1. Problem statement (official template)

For **upay customers, especially first-time and low-literacy users**, **account takeover through reverse-engineered app APIs and coerced transactions driven by scam calls** cause **direct financial loss and loss of trust in the wallet, even though the app already enforces obfuscation, OTP auto-fill, VPN detection and integrity checks**. We will build **Second Thought, a session-authenticity engine** that uses **the clickstream upay already collects (API call order, screen visits, inter-event timing, telemetry completeness, device context, and each user's own history)** to **decide in real time whether a session behaves like the genuine human owner and trigger a graduated intervention (plain-language confirm screen, step-up verification, or hold for analyst review) before the first money-moving call**, with success measured by **the share of fraudulent sessions stopped before money moves, at a false-friction rate on genuine sessions below 2%**.

### Why this is different from a transaction-risk model

A transaction model sees the transfer. By then the attacker already owns the session and the only choices are approve or decline. The behaviour that reveals the attacker (skipped screens, missing telemetry, machine-regular timing, a brand-new device going straight to PIN change, a victim hesitating for minutes on an amount they have never sent to a number they have never used) is visible **five to ten events earlier**. upay already records those steps. Nobody is yet asking whether the steps look like the account's real owner.

### Why AI is material, not a rule

There is no single rule for "this does not look like a human using the app." It is the joint distribution of transition order, dwell times, telemetry completeness, typing speed, and deviation from *this user's* baseline. A velocity-and-new-device rule catches scripted bots but misses the coerced victim entirely, because the victim *is* the human on their own phone. On our holdout the rule baseline recalls 25.8% of coerced-victim sessions; the model recalls 96.6% of them before the money moves.

---

## 2. Nine-step logic chain

| # | Step | Answer |
|---|---|---|
| 1 | **User** — Who experiences the problem? | Three personas. **Customer:** a first-time or low-literacy wallet owner (RMG worker, elderly, rural user) who is either locked out by an API-level takeover or talked into a transfer by a "fake upay office" caller. **Internal user:** the fraud analyst who today sees alerts only after the money has left. **Business:** upay, which refunds, loses trust, and loses transaction growth. |
| 2 | **Problem** — What is difficult, costly, risky? | Attackers reverse-engineer the API and bypass app-level controls (obfuscation, OTP auto-fill, VPN and integrity checks). Scam calls coerce real owners into real transfers, which no device or credential check can catch. **Baseline today:** transaction-level scoring after the transfer request, plus manual review; the session itself is never judged. Consequence: money leaves before any control fires, and refunds or disputes are the only recourse. |
| 3 | **Why now** — Why could AI help now? | upay already runs a step tracker that logs screens, API calls and timestamps per session. That stream is an untapped behavioural signal. Fraud volume rises with the customer base, especially among less literate users. Gradient-boosted models with SHAP make per-event scoring explainable at millisecond latency, so an intervention can happen *inside* the session rather than after it. |
| 4 | **Solution** — What exactly are you building? | A sidecar that consumes the existing event stream, scores each session **per event**, and returns one of four actions through a policy API the app calls before `confirm`: **allow**, **Second Thought screen** (Bangla + English plain-language explanation, confirm or cancel, "I was asked by a caller" route), **step-up** (re-auth or call-back), **hold + analyst queue**. Analyst console shows the event timeline, SHAP reasons, rule trace and an LLM narrative grounded only in structured evidence. Prototype includes a Session Replay Theatre, a phone-frame customer screen, the analyst console, and a live "attack me" button that runs a scripted client against our own API. |
| 5 | **AI role** — What is the model doing? | **Detection**, layered and each layer explainable. L1: first-order Markov flow model trained on human sessions only (unsupervised, catches novel flows). L2: LightGBM session classifier on 47 engineered features across structure, timing, user-baseline and flow signals, with SHAP top reasons. L3: per-user baseline deviation (hour, amount, recipient, hesitation, rhythm) so "unusual for this user" is separated from "unusual for everyone". L4: account-role misuse classifier on 30-day aggregates (personal wallet acting as merchant/agent). L5: Isolation Forest as an unsupervised second opinion. Business rules and thresholds live in a separate policy layer, never inside a prompt. |
| 6 | **Impact** — What outcome should improve? | **Primary metric:** % of fraudulent sessions stopped at or before the first money-moving request. **Guardrail:** false-friction rate on genuine sessions ≤ 2%, overall and per persona. **Secondary:** median events-to-detection, analyst minutes saved via narrative, ৳ protected on the synthetic month. **Holdout result:** 92.5% of fraud sessions stopped before money moved at 2.0% false friction; rules baseline achieves 82.7% recall at 12.1% false friction and 25.8% on coerced victims. |
| 7 | **Data** — What can you safely simulate? | Fully synthetic clickstream, no production or personal data. 3,000 users × 30 days, 64k sessions, 1.16M events. Six human personas with distinct dwell, typing speed, PIN-error rate, usual hours and intent mix. Seven injected attack archetypes: scripted API ATO, OTP-relay takeover, coerced victim, wallet-as-merchant, gambling laundering, emulator farm, and an adaptive attacker with human-like timing. Every distribution is documented in `data/ASSUMPTIONS.md`. Event schema maps one-to-one onto a generic step tracker (session, user, timestamp, event name, gap, device, amount, recipient). |
| 8 | **Validation** — How will you know it works? | **Offline:** 20% holdout split by *user* so per-user baselines cannot leak. AUC and PR-AUC overall and per archetype; recall at a fixed 2% false-friction operating point; detection latency versus first money event; fairness slice of false friction by persona, age band, gender, region and feature-phone (elderly 0.8%, rural low-literacy 1.6%, no slow group above the overall rate); novel-attack test with one archetype held out of training (unsupervised layers alone recall 47.9% of it); adaptive-attacker test; rule baseline comparison. **Online path:** two-week shadow mode on real telemetry, then an A/B of the Second Thought screen measuring reversed transfers, fraud loss, and session abandonment. |
| 9 | **Scale** — What changes with real data? | Zero app changes to start: the engine is a sidecar on telemetry upay already emits; the policy call is added before `confirm` later. Scoring is stateless per request with O(1) incremental feature updates, so it scales horizontally. With real data: recalibrate thresholds to real base rates, retrain from analyst labels in a feedback loop, add device-graph and counterparty-graph features. Governance: behavioural metadata only, no message content or PII in features; human review for every hold; no autonomous permanent block; LLM narrative never sees user free text, only our evidence JSON. |

---

## 3. Responsible AI commitments

- **Privacy:** synthetic data only during the hackathon; in production, features use endpoint names, timing and screen ids, never message content.
- **Fairness:** persona, age, gender, region and device class are excluded from features. Slow users are compared with their own history, so slow is normal for a slow user. False friction is reported per group.
- **Explainability:** SHAP top reasons per alert, rule trace, and a narrative grounded only in structured evidence.
- **Human oversight:** holds route to an analyst queue; the system never permanently blocks an account on its own.
- **Security:** prompt-injection guard (the LLM never receives user-supplied text), adversarial test with a timing-mimicking attacker, user-level holdout against leakage.

## 4. Where to look in the repo

| What | Where |
|---|---|
| Full strategy, threat model, schedule, judge Q&A | `STRATEGY.md` |
| Synthetic data generator and documented assumptions | `data/generate.py`, `data/ASSUMPTIONS.md` |
| Feature engine (works on any prefix of a session) | `ml/features.py` |
| Training, metrics, SHAP, latency, fairness, novel-attack test | `ml/train.py`, `ml/models/metrics.json` |
| Streaming scorer, policy engine, narrative | `api/` |
| Replay Theatre, phone screen, analyst console | `web/` |
| Every prompt used during the build | `PROMPT.md` |
