"""
Train and evaluate Second Thought.

Layers
  L1 MarkovFlow      unsupervised flow likelihood (human sessions only)
  L2 LightGBM        supervised session classifier + SHAP
  L3 user baseline   deviation features (hour_dev, amount_z, recipient_known_ratio, rhythm, hesitation) -> inside L2 and standalone
  L4 LightGBM        account-role misuse (personal wallet acting as merchant/agent)
  L5 IsolationForest unsupervised second opinion on L2 features

Evaluation written to ml/models/metrics.json:
  AUC/PR-AUC, per-archetype recall at a 2% false-friction operating point, fairness slices,
  rule baseline, novel-attack holdout (A5), adaptive attacker (A7), detection latency vs first money call.
"""
from __future__ import annotations
import json, sys, time, warnings
from pathlib import Path
import joblib, numpy as np, pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.features import MarkovFlow, build_dataset, session_features, FEATURE_NAMES, MONEY_API

try:
    import lightgbm as lgb
    def make_clf(spw): return lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=30,
                                                 subsample=0.8, colsample_bytree=0.8, scale_pos_weight=spw, verbose=-1, random_state=7)
    MODEL_KIND = "LightGBM"
except Exception:
    from sklearn.ensemble import HistGradientBoostingClassifier
    def make_clf(spw): return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, class_weight="balanced", random_state=7)
    MODEL_KIND = "HistGradientBoosting"

ROOT = Path(__file__).resolve().parents[1]; DATA = ROOT / "data/out"; OUT = ROOT / "ml/models"; OUT.mkdir(exist_ok=True)
TARGET_FPR = 0.02
BASE_FEATS = [f for f in FEATURE_NAMES]  # all features; demographics are never included
RULE_DESC = "flag if (new_device and amount>=40% cap) or money_per_minute>3 or (new recipient and night and amount>=60% cap)"


def rule_baseline(X):
    return ((X.new_device == 1) & (X.amount_frac_cap >= .4)) | (X.money_per_minute > 3) | \
           ((X.new_recipient_count > 0) & (X.is_night == 1) & (X.amount_frac_cap >= .6))


def threshold_for_fpr(scores_human, fpr):
    return float(np.quantile(scores_human, 1 - fpr))


def per_arch_recall(df, flag_col):
    return {a: round(float(df.loc[df.archetype == a, flag_col].mean()), 4) for a in sorted(df.archetype.unique()) if a != "human"}


def main():
    t0 = time.time()
    ev = pd.read_parquet(DATA / "events.parquet"); se = pd.read_parquet(DATA / "sessions.parquet"); acc = pd.read_parquet(DATA / "accounts.parquet")
    print(f"loaded events={len(ev):,} sessions={len(se):,}")

    # ---- L1 Markov on human TRAIN sessions
    human_train_ids = set(se[(se.split == "train") & (se.label == "human")].session_id)
    seqs = [g.event.tolist() for sid, g in ev[ev.session_id.isin(human_train_ids)].sort_values(["session_id", "idx"]).groupby("session_id", sort=False)]
    markov = MarkovFlow().fit(seqs)
    print(f"markov fitted on {len(seqs):,} human sessions, vocab={len(markov.vocab)}")

    # ---- features (chronological per user, profile = user's own past)
    device_counts = se.groupby("device_id").user_id.nunique().to_dict()
    fraud_test_ids = set(se[(se.split == "test") & (se.label == "fraud")].session_id)
    X, profiles, snaps = build_dataset(ev, se, markov, device_counts, snapshot_ids=fraud_test_ids, progress=True)
    meta = se.set_index("session_id").loc[X.index]
    y = (meta.label == "fraud").astype(int)
    tr, te = meta.split == "train", meta.split == "test"
    X.to_parquet(OUT / "features.parquet")
    print(f"features built: {X.shape} in {time.time()-t0:.0f}s")

    # ---- L2 supervised
    spw = float((y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1))
    clf = make_clf(spw).fit(X[tr], y[tr])
    p = pd.Series(clf.predict_proba(X)[:, 1], index=X.index)
    # ---- L5 isolation forest on human train
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=7).fit(X[tr & (y == 0)])
    iso_s = pd.Series(-iso.score_samples(X), index=X.index)
    # ---- L1 standalone
    mk_s = X.mk_mean_nll

    test = meta[te].copy(); test["p"] = p[te]; test["iso"] = iso_s[te]; test["mk"] = mk_s[te]; test["y"] = y[te]
    human_te = test[test.y == 0]
    thr = threshold_for_fpr(human_te.p, TARGET_FPR); thr1 = threshold_for_fpr(human_te.p, 0.01)
    test["flag"] = (test.p >= thr).astype(int)
    test["rule"] = rule_baseline(X[te]).astype(int).values
    # unsupervised ensemble (no labels): either L1 or L5 above its 99th human percentile
    u_thr_mk = threshold_for_fpr(human_te.mk, .01); u_thr_iso = threshold_for_fpr(human_te.iso, .01)
    test["unsup"] = ((test.mk >= u_thr_mk) | (test.iso >= u_thr_iso)).astype(int)

    metrics = dict(
        model=MODEL_KIND, n_train=int(tr.sum()), n_test=int(te.sum()), fraud_rate_test=round(float(test.y.mean()), 4),
        auc=round(float(roc_auc_score(test.y, test.p)), 4), pr_auc=round(float(average_precision_score(test.y, test.p)), 4),
        auc_markov_only=round(float(roc_auc_score(test.y, test.mk)), 4), auc_isoforest_only=round(float(roc_auc_score(test.y, test.iso)), 4),
        operating_point=dict(target_false_friction=TARGET_FPR, threshold=round(thr, 4), threshold_1pct=round(thr1, 4),
                             recall=round(float(test.loc[test.y == 1, "flag"].mean()), 4),
                             precision=round(float(test.loc[test.flag == 1, "y"].mean()), 4),
                             false_friction=round(float(human_te.p.ge(thr).mean()), 4)),
        recall_by_archetype=per_arch_recall(test, "flag"),
        operating_curve={f"{fp:.3%}": dict(threshold=round(threshold_for_fpr(human_te.p, fp), 4),
                                           recall=round(float((test.loc[test.y == 1, "p"] >= threshold_for_fpr(human_te.p, fp)).mean()), 4),
                                           recall_by_archetype={a: round(float((test.loc[test.archetype == a, "p"] >= threshold_for_fpr(human_te.p, fp)).mean()), 4)
                                                                for a in sorted(test.archetype.unique()) if a != "human"})
                         for fp in [0.0025, 0.005, 0.01, 0.02]},
        rule_baseline=dict(description=RULE_DESC, recall=round(float(test.loc[test.y == 1, "rule"].mean()), 4),
                           false_friction=round(float(test.loc[test.y == 0, "rule"].mean()), 4), recall_by_archetype=per_arch_recall(test, "rule")),
        unsupervised_only=dict(description="L1 Markov OR L5 IsolationForest above 99th human percentile (no labels used)",
                               recall=round(float(test.loc[test.y == 1, "unsup"].mean()), 4),
                               false_friction=round(float(test.loc[test.y == 0, "unsup"].mean()), 4), recall_by_archetype=per_arch_recall(test, "unsup")),
    )

    # ---- fairness: false friction by slice (genuine sessions only)
    fair = {}
    for col in ["persona", "gender", "region", "feature_phone"]:
        fair[col] = {str(k): round(float(v), 4) for k, v in human_te.assign(flag=human_te.p >= thr).groupby(col).flag.mean().items()}
    human_te2 = human_te.assign(age_band=pd.cut(human_te.age, [0, 25, 40, 55, 100], labels=["18-25", "26-40", "41-55", "56+"]), flag=human_te.p >= thr)
    fair["age_band"] = {str(k): round(float(v), 4) for k, v in human_te2.groupby("age_band", observed=True).flag.mean().items()}
    metrics["fairness_false_friction_by_slice"] = fair

    # ---- novel-attack holdout: drop A5 from training, can L2 / unsupervised still find it?
    keep = tr & (meta.archetype != "A5_gambling_laundering")
    clf_nov = make_clf(spw).fit(X[keep], y[keep])
    p_nov = pd.Series(clf_nov.predict_proba(X[te])[:, 1], index=X[te].index)
    thr_nov = threshold_for_fpr(p_nov[test.y == 0], TARGET_FPR)
    a5 = test.archetype == "A5_gambling_laundering"
    metrics["novel_attack_holdout"] = dict(
        held_out="A5_gambling_laundering",
        recall_supervised_never_saw_A5=round(float((p_nov[a5] >= thr_nov).mean()), 4),
        recall_unsupervised_L1_L5=round(float(test.loc[a5, "unsup"].mean()), 4),
        recall_supervised_with_A5=round(float(test.loc[a5, "flag"].mean()), 4))

    # ---- SHAP
    import shap
    expl = shap.TreeExplainer(clf)
    sv = expl.shap_values(X[te])
    sv = sv[1] if isinstance(sv, list) else sv
    gi = pd.Series(np.abs(sv).mean(0), index=X.columns).sort_values(ascending=False)
    metrics["shap_global_top10"] = {k: round(float(v), 4) for k, v in gi.head(10).items()}
    shap_by_arch = {}
    for a in sorted(test.archetype.unique()):
        if a == "human": continue
        m = (test.archetype == a).values
        s = pd.Series(sv[m].mean(0), index=X.columns).sort_values(ascending=False)
        shap_by_arch[a] = {k: round(float(v), 4) for k, v in s.head(5).items()}
    metrics["shap_top5_by_archetype"] = shap_by_arch

    # ---- detection latency on fraud test sessions (streaming prefixes)
    cols = ["event", "dt_ms", "amount", "recipient_id", "pin_error", "ok", "ts"]
    ev_te = ev[ev.session_id.isin(fraud_test_ids)].sort_values(["session_id", "idx"])
    lat_rows = []
    for sid, g in ev_te.groupby("session_id", sort=False):
        evs = g[cols].to_dict("records"); prof, nd = snaps[sid]
        dcount = device_counts.get(g.device_id.iloc[0], 1)
        first_money = next((i for i, e in enumerate(evs) if e["event"] in MONEY_API and e["ok"]), -1)  # first SUCCESSFUL money call = money moves
        first_attempt = next((i for i, e in enumerate(evs) if e["event"] in MONEY_API), -1)
        feats = [session_features(evs[:k], prof, markov, dcount, nd) for k in range(1, len(evs) + 1)]
        probs = clf.predict_proba(pd.DataFrame(feats)[FEATURE_NAMES])[:, 1]
        hit = next((k + 1 for k, pr in enumerate(probs) if pr >= thr), None)
        lat_rows.append(dict(session_id=sid, archetype=meta.loc[sid, "archetype"], n=len(evs), first_money_idx=first_money,
                             detect_at=hit, money=float(meta.loc[sid, "money_total"]),
                             before_attempt=bool(hit is not None and first_attempt >= 0 and hit <= first_attempt),
                             at_or_before_request=bool(hit is not None and first_money >= 0 and hit <= first_money + 1)))
    lat = pd.DataFrame(lat_rows); lat.to_parquet(OUT / "latency.parquet")
    det = lat[lat.detect_at.notna()]
    metrics["detection_latency"] = dict(
        fraud_sessions=int(len(lat)), detected=int(len(det)),
        stopped_at_or_before_first_money_request=round(float(lat.at_or_before_request.mean()), 4),
        detected_before_first_money_attempt=round(float(lat.before_attempt.mean()), 4),
        median_events_to_detect=float(det.detect_at.median()) if len(det) else None,
        median_first_money_idx=float(lat.first_money_idx.median()),
        by_archetype={a: dict(stopped_before_money=round(float(d.at_or_before_request.mean()), 4), median_detect_event=float(d.detect_at.median()) if d.detect_at.notna().any() else None,
                              median_money_event=float(d.first_money_idx.median() + 1))
                      for a, d in lat.groupby("archetype")},
        money_at_risk_bdt=round(float(lat.money.sum()), 0), money_protected_bdt=round(float(lat.loc[lat.at_or_before_request, "money"].sum()), 0),
    )

    # ---- L4 account role
    acols = ["inbound_tx_30d", "unique_senders_30d", "outbound_tx_30d", "cashout_count_30d", "round_amount_ratio", "night_ratio",
             "median_inbound_amt", "sender_concentration", "cashout_to_inbound", "is_registered_merchant"]
    atr, ate = acc.split == "train", acc.split == "test"
    aclf = make_clf(float((acc.label_role_misuse[atr] == 0).sum() / max(acc.label_role_misuse[atr].sum(), 1))).fit(acc.loc[atr, acols], acc.loc[atr, "label_role_misuse"])
    ap = aclf.predict_proba(acc.loc[ate, acols])[:, 1]
    metrics["account_role_misuse"] = dict(n_test=int(ate.sum()), positives_test=int(acc.loc[ate, "label_role_misuse"].sum()),
                                          auc=round(float(roc_auc_score(acc.loc[ate, "label_role_misuse"], ap)), 4) if acc.loc[ate, "label_role_misuse"].sum() else None,
                                          pr_auc=round(float(average_precision_score(acc.loc[ate, "label_role_misuse"], ap)), 4) if acc.loc[ate, "label_role_misuse"].sum() else None)

    # ---- save artefacts
    joblib.dump(clf, OUT / "session_clf.joblib"); joblib.dump(iso, OUT / "isoforest.joblib"); joblib.dump(aclf, OUT / "account_clf.joblib")
    (OUT / "markov.json").write_text(json.dumps(markov.to_dict()))
    (OUT / "profiles.json").write_text(json.dumps({u: pr.to_dict() for u, pr in profiles.items()}))
    (OUT / "thresholds.json").write_text(json.dumps(dict(session=thr, session_1pct=thr1, markov=u_thr_mk, iso=u_thr_iso, features=FEATURE_NAMES, account_features=acols)))
    test[["user_id", "persona", "archetype", "y", "p", "iso", "mk", "flag", "rule", "unsup", "money_total", "first_money_idx", "n_events"]].to_parquet(OUT / "test_scores.parquet")
    metrics["train_seconds"] = round(time.time() - t0, 1)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

    # ---- plots
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 3, figsize=(15, 4))
        pr_, rc_, _ = precision_recall_curve(test.y, test.p); ax[0].plot(rc_, pr_); ax[0].set_title(f"PR curve (AP={metrics['pr_auc']})"); ax[0].set_xlabel("recall"); ax[0].set_ylabel("precision")
        ra = metrics["recall_by_archetype"]; rb = metrics["rule_baseline"]["recall_by_archetype"]
        xs = np.arange(len(ra)); ax[1].bar(xs - .2, list(ra.values()), .4, label="Second Thought"); ax[1].bar(xs + .2, [rb[k] for k in ra], .4, label="rule baseline")
        ax[1].set_xticks(xs); ax[1].set_xticklabels([k.split("_")[0] for k in ra]); ax[1].set_title("Recall by archetype @2% false friction"); ax[1].legend()
        gi.head(12)[::-1].plot.barh(ax=ax[2]); ax[2].set_title("Global SHAP importance")
        plt.tight_layout(); plt.savefig(OUT / "eval.png", dpi=130)
    except Exception as e:
        print("plot failed:", e)


if __name__ == "__main__":
    main()
