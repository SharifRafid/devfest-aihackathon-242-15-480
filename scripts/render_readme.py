"""Render README.md from README.template.md + ml/models/metrics.json so every number in the README is reproducible."""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
m = json.loads((ROOT / "ml/models/metrics.json").read_text())
pct = lambda v: f"{v*100:.1f}%"
A = {"A1_scripted_api": "A1 Scripted ATO via reverse-engineered API", "A2_otp_relay_takeover": "A2 OTP-relay / SIM-swap takeover", "A3_coerced_victim": "A3 Coerced victim on a scam call",
     "A5_gambling_laundering": "A5 Gambling / fake-purchase laundering", "A6_emulator_farm": "A6 Emulator farm", "A7_adaptive_scripted": "A7 Adaptive attacker (human-like timing)"}
op, rb, un, lat, nov, fair = m["operating_point"], m["rule_baseline"], m["unsupervised_only"], m["detection_latency"], m["novel_attack_holdout"], m["fairness_false_friction_by_slice"]
rows = "\n".join(f"| {A[a]} | {pct(m['recall_by_archetype'][a])} | {pct(un['recall_by_archetype'][a])} | {pct(rb['recall_by_archetype'][a])} | {pct(lat['by_archetype'][a]['stopped_before_money'])} | {lat['by_archetype'][a]['median_detect_event']:.0f} / {lat['by_archetype'][a]['median_money_event']:.0f} |" for a in A)
curve = "\n".join(f"| {k} | {v['threshold']} | {pct(v['recall'])} | {pct(v['recall_by_archetype']['A3_coerced_victim'])} | {pct(v['recall_by_archetype']['A5_gambling_laundering'])} |" for k, v in m["operating_curve"].items())
fair_rows = "\n".join(f"| {k} | {pct(v)} |" for k, v in {**{f"persona: {k}": v for k, v in fair['persona'].items()}, **{f"age {k}": v for k, v in fair['age_band'].items()}, **{f"feature phone: {k}": v for k, v in fair['feature_phone'].items()}, **{f"gender: {k}": v for k, v in fair['gender'].items()}}.items())
shap_rows = "\n".join(f"| {k} | {v} |" for k, v in m["shap_global_top10"].items())
vals = dict(AUC=m["auc"], PRAUC=m["pr_auc"], AUC_MK=m["auc_markov_only"], AUC_ISO=m["auc_isoforest_only"], RECALL=pct(op["recall"]), FF=pct(op["false_friction"]), PREC=pct(op["precision"]), THR=op["threshold"],
            RULE_RECALL=pct(rb["recall"]), RULE_FF=pct(rb["false_friction"]), RULE_A3=pct(rb["recall_by_archetype"]["A3_coerced_victim"]), UNSUP_RECALL=pct(un["recall"]), UNSUP_FF=pct(un["false_friction"]),
            STOPPED=pct(lat["stopped_at_or_before_first_money_request"]), BEFORE_ATTEMPT=pct(lat["detected_before_first_money_attempt"]), MED_DETECT=f"{lat['median_events_to_detect']:.0f}", MED_MONEY=f"{lat['median_first_money_idx']+1:.0f}",
            AT_RISK=f"{lat['money_at_risk_bdt']:,.0f}", PROTECTED=f"{lat['money_protected_bdt']:,.0f}", NOV_SUP=pct(nov["recall_supervised_never_saw_A5"]), NOV_UNSUP=pct(nov["recall_unsupervised_L1_L5"]),
            ACC_AUC=m["account_role_misuse"]["auc"], ACC_POS=m["account_role_misuse"]["positives_test"], NTRAIN=f"{m['n_train']:,}", NTEST=f"{m['n_test']:,}", FRAUD_RATE=pct(m["fraud_rate_test"]),
            ARCH_TABLE=rows, CURVE_TABLE=curve, FAIR_TABLE=fair_rows, SHAP_TABLE=shap_rows, TRAIN_S=m["train_seconds"], MODEL=m["model"])
t = (ROOT / "README.template.md").read_text()
out = re.sub(r"\{\{(\w+)\}\}", lambda mm: str(vals[mm.group(1)]), t)
(ROOT / "README.md").write_text(out); print("README.md rendered")
