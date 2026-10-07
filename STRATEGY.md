# AI Hackathon 2026 (DIU CPC × upay) — 4‑Hour Winning Strategy

Deadline math: 240 minutes. Written 2026-10-07 ~09:00. Hard stop: whatever the organizers announced (no extensions, rule 6.2).

## 1. What the rules actually mean for you

| Rule | Implication |
|---|---|
| 5.1 No limit on AI tools, own account only | Use Claude Code at full tilt. Never log into anyone else's account. |
| 5.6 / 7.4 Judges may demand prompt/dev history | `PROMPT.md` + commit messages with prompts = ready-made evidence. Keep them clean. Do not delete history. |
| 4.1–4.2 No external human help, no sharing | Don't ask friends / group chats. Don't paste code to other teams. |
| 7.2 Don't manipulate judging infra | No tricks with hidden tests / system prompts. |
| 8.2–8.3 Problem statement defines format; judging may include **live demo + technical questioning** | **Confirm the exact deliverable NOW** (repo link? video? slides? form?). The guideline PDF never states a submission format or deadline. Ask via the official clarification channel (10.1). Prepare for a live demo AND a recorded backup video. |
| 11 Privacy: synthetic/public data only | Never scrape real user data. Document every synthetic assumption. Keep a holdout test set. |
| 14 Responsible AI | No autonomous approve/deny of money decisions. Human-in-the-loop, explainability, fairness check, prompt-injection guard. Cheap 5% + it feeds "scalability" and "AI depth" scores. |

## 2. How judges score (and where the points are)

| Criterion | Weight | How to bank it in 4h |
|---|---|---|
| Problem relevance | 20% | One sharp sentence in the official template. Bangladesh‑specific MFS pain, not generic fintech. |
| AI/ML depth | 20% | A **real trained model** with holdout metrics + SHAP, not an LLM wrapper. LLM only as an explanation layer grounded in structured evidence (the PDF says exactly this). |
| Business / customer impact | 20% | Quantified in ৳ and % with a stated baseline, using your synthetic experiment (treatment vs control). |
| Prototype quality | 15% | End-to-end click-through: data → model → API → UI → action. Must not crash in demo. |
| Innovation | 10% | Reframe the problem (PDF: "redefine the problem rather than improve a familiar workflow"). |
| Scalability & integration | 10% | Clean API boundary, "what changes with real upay data" section, feedback loop. |
| Responsible AI & security | 5% | Fairness slice, explainability, human review, injection guard, no PII. |

**60% of the score is framing + credible AI + measured impact.** Only 15% is the UI. Budget your time accordingly: do not spend 2.5 hours on frontend polish.

The PDF's own "good project test": **What happened? Why is it risky/important? What should upay do next?** Every screen should answer those three.

## 3. Track choice

- **Track 01 Fraud** — most teams will pick it. Crowded, judges will have seen 10 XGBoost-on-synthetic-fraud demos.
- **Track 03 Customer Innovation & Financial Independence** — the PDF calls it the *"flagship differentiation track."* Customer-facing, demo-friendly, Bangla-friendly, and most teams will under-build the ML part (treat it as a chatbot). That gap is your edge.
- **Track 05 Agent liquidity** — strong business case, uncrowded, but weak demo visuals and harder to explain to a mixed panel.

**Recommendation: Track 03, built with Track‑01‑grade ML rigor.**

### The product: "upay Sohojpath" (working title) — a Financial Health Copilot inside the upay app

> For low/middle-income upay users who run short before month-end, unpredictable cash-flow causes repeated cash-out dependency and missed savings goals. We will build an AI financial-health copilot that uses a user's own wallet transaction history to forecast month-end shortfall risk, explain the drivers, and turn a savings goal into a feasible plan, with success measured by shortfall-weeks avoided and savings-goal completion rate in a simulated treatment/control experiment.

Four AI components (each one is a real model, each has a metric):
1. **Cash-flow shortfall forecaster** — gradient-boosted classifier/regressor on weekly engineered features (inflow regularity, cash-out ratio, bill timing, balance trajectory). Metric: AUC / MAE on holdout. SHAP for "why".
2. **Spending categorizer + avoidable-spend anomaly detector** — Isolation Forest / z-score per category on the user's own baseline. Metric: precision on injected anomalies.
3. **Savings-goal planner** — constrained optimization over the forecast: feasible weekly contribution, trade-offs, date when goal is hit. ("I need ৳30,000 in six months" is literally the PDF example.)
4. **Explainable credit-readiness signal** — logistic model on behavioral consistency features, SHAP-explained, explicitly *not* a lending decision (PDF requirement).

Plus an **LLM narration layer** (Bangla + English) that receives only the structured JSON outputs of 1–4 and writes plain-language coaching. Deterministic templated fallback if the API is down. Prompt-injection guard on any free-text input.

Synthetic data: 2,000 users × 6 months, 5 personas (salaried, student, small merchant, remittance recipient, gig worker), with **injected** patterns: salary cycles, Eid/month-end spikes, cash-out dependency, churn, savers vs non-savers. Documented assumptions in `data/ASSUMPTIONS.md`. 20% holdout never touched by training.

Impact story (computed from the simulation, not hand-waved): users who get a shortfall warning + plan one week early vs. control → X% fewer shortfall weeks, Y% higher goal completion, Z% lower cash-out volume → for upay: more balance retained in wallet, more digital transactions, higher retention. State the economics per 1M users.

## 4. Stack (speed-optimized for one person + Claude Code)

- **Data + ML:** Python, pandas, scikit-learn, LightGBM, SHAP. Notebook-free; plain scripts so it's reproducible (`make data`, `make train`).
- **API:** FastAPI (`/users/{id}/health`, `/forecast`, `/plan`, `/explain`). Business rules separated from model inference (PDF architecture expectation).
- **Frontend:** Vite + React + Tailwind, rendered as a phone-frame so it looks like a feature inside the upay app. One analyst view (ops/upay side) + one customer view.
- **LLM:** Anthropic API with your own key; small, grounded prompts; fallback templates.
- **Docs:** README with the 9‑step logic chain, architecture diagram, metrics table, Responsible AI section, "path to real upay data". 6‑slide deck. 2‑minute screen-recorded demo video as insurance.

## 5. Minute-by-minute plan (240 min)

| Window | Deliverable | Done when |
|---|---|---|
| 0:00–0:15 | Lock idea. Write README problem statement (template) + 9‑step logic chain. Ask organizers the submission format. | README has the one-liner and the table. |
| 0:15–0:45 | Synthetic data generator with personas + injected patterns + holdout split + ASSUMPTIONS.md | `python data/generate.py` → CSVs, sanity plots. |
| 0:45–1:35 | Models 1–4 trained, holdout metrics saved to `models/metrics.json`, SHAP top‑features, fairness slice (gender/region/persona) | `python ml/train.py` runs clean end-to-end. |
| 1:35–2:05 | FastAPI serving all four + LLM explain endpoint with fallback + injection guard | `curl` every endpoint works. |
| 2:05–3:00 | React UI: customer phone view (health score, shortfall warning, why, plan, Bangla toggle) + analyst view (cohort metrics, fairness table) | Click-through demo with no console errors. |
| 3:00–3:30 | Impact simulation numbers → README + deck (6 slides) + architecture diagram | Deck exported to PDF. |
| 3:30–3:45 | Record 2‑min demo video. Final README polish. | Video file in repo or Drive link. |
| 3:45–4:00 | Buffer. Submission checklist. Final `/push`. Verify the public link opens in incognito. | Submitted. |

Cut order if behind schedule: (1) analyst view, (2) credit-readiness model, (3) Bangla toggle, (4) anomaly detector. Never cut: forecaster + plan + explanation + README metrics.

## 6. Demo / Q&A prep (judges can do live technical questioning)

Have crisp answers for: Why is this not just a rule ("balance < bills → warn")? → show the model beats the rule baseline on holdout. What happens with real upay data? → feature schema maps 1:1 to MFS transaction logs; retrain + calibrate; A/B test design already written. How do you prevent harmful nudges? → no spending promotion, no autonomous decisions, explanations separate predictions from assumptions. Fairness? → show the slice table. Prompt injection? → show the guard and the grounded-JSON-only LLM input.

## 7. Workflow tooling already in place

- Every prompt you type is appended to `PROMPT.md` (hook). This is your rule‑5.6 evidence.
- `/push` commits + pushes with changed files and prompts in the message. `/autopush status|stop|start N` controls the 15‑min background loop (already running).
