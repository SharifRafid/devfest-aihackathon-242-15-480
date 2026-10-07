"""
Optional typed-decision layer (TypeSafe Jev, a "System One" model that returns calibrated typed
decisions instead of text). Used only to choose the intervention tier from structured evidence.
Falls back to the local policy engine when JEV_API_KEY is not set or the call fails.

Endpoint shape per public docs: POST https://api.typesafe.ai/v1/systemone
  {"model": "typesafe/jev-latest", "state": {...}, "questions": {id: {"type": "choice|score|noul", ...}}}
"""
from __future__ import annotations
import os, httpx

JEV_URL = os.getenv("JEV_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-latest")


def available() -> bool:
    return bool(os.getenv("JEV_API_KEY"))


def decide_with_jev(evidence: dict) -> dict | None:
    if not available(): return None
    body = {
        "model": JEV_MODEL,
        "state": evidence,
        "questions": {
            "intervention": {"type": "choice", "instructions": "Given the session evidence, choose the least intrusive intervention that protects the customer.",
                              "choices": ["allow", "second_thought", "step_up", "hold"]},
            "coerced_genuine_user": {"type": "noul", "instructions": "Is this most likely a genuine customer being coerced by a scammer rather than an attacker operating the account?"},
            "analyst_priority": {"type": "score", "instructions": "Priority for human review, 1 (low) to 5 (urgent).", "min": 1, "max": 5},
        },
    }
    try:
        r = httpx.post(JEV_URL, json=body, headers={"Authorization": f"Bearer {os.environ['JEV_API_KEY']}"}, timeout=5.0)
        r.raise_for_status(); a = r.json().get("answers", {})
        return dict(tier=a["intervention"].get("choice"), coerced_p=a.get("coerced_genuine_user", {}).get("noul"),
                    priority=a.get("analyst_priority", {}).get("score"), decided_by="jev", elapsed_ms=r.json().get("elapsedMs"))
    except Exception as e:  # never let an optional dependency break the decision path
        return {"error": str(e)[:200], "decided_by": "jev_failed"}
