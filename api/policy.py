"""
Policy engine — business rules kept deliberately separate from the ML layer.

Input: the structured evidence a scorer produced for a session prefix.
Output: a graduated, explainable intervention. Never an autonomous permanent block.

Tiers
  allow          nothing happens
  second_thought customer-facing plain-language confirm screen + 30 s cooling period (used when the
                 human is probably genuine but the situation looks like a scam — A3)
  step_up        re-authentication / call-back before the money-moving call executes
  hold           transaction held, case queued for a human analyst (release / step-up / freeze)

An optional typed-decision model (Jev) can replace the tier choice; see jev_adapter.py.
"""
from __future__ import annotations

REASON_TEXT = {
    "frac_new_recipient": ("You have never sent money to this number before.", "আপনি আগে কখনো এই নম্বরে টাকা পাঠাননি।"),
    "new_recipient_count": ("You have never sent money to this number before.", "আপনি আগে কখনো এই নম্বরে টাকা পাঠাননি।"),
    "recipient_known_ratio": ("This recipient is not one of your usual contacts.", "এই প্রাপক আপনার পরিচিত কারো নম্বর নয়।"),
    "money_max": ("This amount is much larger than what you usually send.", "এই পরিমাণ আপনার স্বাভাবিক লেনদেনের চেয়ে অনেক বেশি।"),
    "money_total": ("This amount is much larger than what you usually send.", "এই পরিমাণ আপনার স্বাভাবিক লেনদেনের চেয়ে অনেক বেশি।"),
    "amount_frac_cap": ("This is close to your daily limit.", "এটি আপনার দৈনিক সীমার কাছাকাছি।"),
    "amount_z": ("This amount is unusual for you.", "এই পরিমাণ আপনার জন্য অস্বাভাবিক।"),
    "is_night": ("It is very late at night.", "এখন অনেক রাত।"),
    "hour_dev": ("You do not usually use upay at this time.", "আপনি সাধারণত এই সময়ে উপায় ব্যবহার করেন না।"),
    "hesitation_ratio": ("You paused much longer than usual before confirming.", "নিশ্চিত করার আগে আপনি স্বাভাবিকের চেয়ে অনেক বেশি সময় নিয়েছেন।"),
    "pin_errors": ("Your PIN was entered wrong more than once.", "আপনার পিন একাধিকবার ভুল হয়েছে।"),
    "new_device": ("This is a phone you have not used before.", "এই ফোনটি আপনি আগে ব্যবহার করেননি।"),
    "has_pinchange": ("Your PIN was just changed.", "আপনার পিন এইমাত্র পরিবর্তন হয়েছে।"),
    "has_add_beneficiary": ("A new beneficiary was just added.", "এইমাত্র একটি নতুন প্রাপক যোগ করা হয়েছে।"),
    "mk_mean_nll": ("This session does not follow the app's normal flow.", "এই সেশনটি অ্যাপের স্বাভাবিক ধাপ অনুসরণ করছে না।"),
    "mk_min_logp": ("This session does not follow the app's normal flow.", "এই সেশনটি অ্যাপের স্বাভাবিক ধাপ অনুসরণ করছে না।"),
    "mk_n_unseen": ("This session contains steps the app never produces.", "এই সেশনে এমন ধাপ আছে যা অ্যাপ কখনো তৈরি করে না।"),
    "no_telemetry": ("The traffic is missing signals the real app always sends.", "আসল অ্যাপ যে সংকেত পাঠায়, তা এখানে অনুপস্থিত।"),
    "telemetry_ratio": ("The traffic is missing signals the real app always sends.", "আসল অ্যাপ যে সংকেত পাঠায়, তা এখানে অনুপস্থিত।"),
    "screen_ratio": ("Money is moving without the app's screens being shown.", "অ্যাপের স্ক্রিন না দেখিয়েই টাকা পাঠানো হচ্ছে।"),
    "api_only_prefix": ("Money is moving without the app's screens being shown.", "অ্যাপের স্ক্রিন না দেখিয়েই টাকা পাঠানো হচ্ছে।"),
    "money_without_pin_screen": ("A transfer was requested without the PIN screen.", "পিন স্ক্রিন ছাড়াই টাকা পাঠানোর অনুরোধ এসেছে।"),
    "dt_cv": ("The timing between actions is machine-like.", "কাজগুলোর মধ্যে সময়ের ব্যবধান যন্ত্রের মতো।"),
    "frac_dt_lt_300": ("Actions are happening faster than a person can tap.", "একজন মানুষ যত দ্রুত চাপতে পারে তার চেয়ে দ্রুত কাজ হচ্ছে।"),
    "dt_min": ("Actions are happening faster than a person can tap.", "একজন মানুষ যত দ্রুত চাপতে পারে তার চেয়ে দ্রুত কাজ হচ্ছে।"),
    "ms_per_char_min": ("Typing is faster than humanly possible.", "টাইপিং মানুষের পক্ষে সম্ভবের চেয়ে দ্রুত।"),
    "impossible_typing": ("Typing is faster than humanly possible.", "টাইপিং মানুষের পক্ষে সম্ভবের চেয়ে দ্রুত।"),
    "money_per_minute": ("Several transfers in a very short time.", "খুব অল্প সময়ে একাধিক লেনদেন।"),
    "device_user_count": ("This device is used by many different accounts.", "এই ডিভাইসটি অনেকগুলো অ্যাকাউন্ট ব্যবহার করছে।"),
    "rhythm_ratio": ("The pace of this session is unlike your usual pace.", "এই সেশনের গতি আপনার স্বাভাবিক গতির মতো নয়।"),
    "duration_s": ("The session is unusually short for what it did.", "যা করা হয়েছে তার তুলনায় সেশনটি অস্বাভাবিক ছোট।"),
}

AUTOMATION_FEATS = {"no_telemetry", "api_only_prefix", "money_without_pin_screen", "screen_ratio", "mk_n_unseen", "frac_dt_lt_300",
                    "dt_min", "ms_per_char_min", "impossible_typing", "device_user_count", "dt_cv", "login_without_screen"}


def human_likeness(f: dict) -> float:
    """0..1 — does the traffic look like it was produced by the genuine app in human hands?"""
    s = 1.0
    if f.get("api_only_prefix"): s -= .6
    if f.get("no_telemetry"): s -= .3
    if f.get("money_without_pin_screen", 0) > 0: s -= .3
    if f.get("impossible_typing", 0) > 0: s -= .3
    if f.get("frac_dt_lt_300", 0) > .5: s -= .2
    if f.get("device_user_count", 1) > 3: s -= .3
    if f.get("screen_ratio", 0) < .3: s -= .2
    return max(0.0, min(1.0, s))


def decide(p: float, feats: dict, top_reasons: list[str], thr: dict) -> dict:
    """thr: {"session": 2%-false-friction threshold}. Returns tier, rationale, customer message (en/bn), analyst actions."""
    t2 = thr["session"]
    hl = human_likeness(feats)
    coercion_like = (hl >= .7 and feats.get("frac_new_recipient", 0) > 0 and
                     (feats.get("amount_frac_cap", 0) >= .25 or feats.get("hesitation_ratio", 1) >= 1.8 or feats.get("pin_errors", 0) >= 1))
    money_pending = feats.get("n_money", 0) > 0 or feats.get("frac_new_recipient", 0) > 0

    if p < t2:
        tier, why = "allow", "Score below the 2% false-friction operating point."
    elif hl < .4 and p >= .6:
        tier, why = "hold", "Traffic does not look like the genuine app (missing screens/telemetry or machine timing) and risk is high. Hold and queue for an analyst."
    elif feats.get("new_device") and p >= .6:
        tier, why = "step_up", "High risk from a device this user has never used. Re-verify the owner before the money-moving call executes."
    elif coercion_like:
        tier, why = "second_thought", "The person looks genuine but the situation matches a scam pattern (first-ever recipient, unusual amount, hesitation). Talk to the customer, do not block them."
        if feats.get("amount_frac_cap", 0) >= .6 and p >= .85: tier, why = "step_up", why + " Amount near the daily limit, add a call-back."
    elif p >= .85:
        tier, why = "step_up", "High risk score; re-verify before execution."
    else:
        tier, why = "second_thought", "Moderate risk; ask the customer to confirm with a plain-language explanation."

    reasons = []
    for r in top_reasons:
        if hl >= .7 and r in AUTOMATION_FEATS: continue   # a genuine human must never be told "the app's screens were not shown"
        if r in REASON_TEXT and REASON_TEXT[r] not in reasons: reasons.append(REASON_TEXT[r])
        if len(reasons) == 3: break
    en = [r[0] for r in reasons]; bn = [r[1] for r in reasons]
    msg = {
        "allow": ("", ""),
        "second_thought": ("Take a second. Did someone ask you to do this over the phone? upay staff never ask you to send money.",
                           "একটু থামুন। কেউ কি ফোনে আপনাকে এটি করতে বলেছে? উপায় কর্মীরা কখনো টাকা পাঠাতে বলেন না।"),
        "step_up": ("For your safety we need to verify it is you before this goes through.",
                    "আপনার নিরাপত্তার জন্য এটি সম্পন্ন করার আগে আমাদের নিশ্চিত হতে হবে যে এটি আপনিই।"),
        "hold": ("This transaction has been paused for a security review. Our team will contact you.",
                 "নিরাপত্তা পর্যালোচনার জন্য এই লেনদেনটি সাময়িকভাবে স্থগিত করা হয়েছে। আমাদের দল আপনার সাথে যোগাযোগ করবে।"),
    }[tier]
    return dict(tier=tier, rationale=why, human_likeness=round(hl, 2), coercion_like=bool(coercion_like), money_pending=bool(money_pending),
                reasons_en=en, reasons_bn=bn, message_en=msg[0], message_bn=msg[1],
                analyst_actions=["release", "request_step_up", "freeze_for_review", "call_customer"] if tier in ("hold", "step_up") else ["release"],
                cooling_seconds=30 if tier == "second_thought" else 0, decided_by="policy_rules")
