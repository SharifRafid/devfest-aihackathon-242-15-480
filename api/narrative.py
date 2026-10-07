"""
Analyst narrative. The LLM only ever sees our structured evidence JSON — never free text typed by a
customer or attacker — so there is no prompt-injection surface. Deterministic template fallback when
no API key is configured or the call fails. Predictions, assumptions and generated text are labelled
separately in the output (PDF §14 transparency).
"""
from __future__ import annotations
import json, os

MODEL = os.getenv("NARRATIVE_MODEL", "claude-sonnet-5-5")
SYSTEM = ("You are a fraud-investigation assistant for a mobile financial service in Bangladesh. You receive ONLY structured evidence "
          "produced by a scoring system. Write a 4-sentence investigation summary for a human analyst: what happened, why it was "
          "flagged, what kind of actor this most likely is, and the recommended next step. Do not invent facts not in the evidence. "
          "Mark anything uncertain as such. Plain English.")


def template(ev: dict) -> str:
    f = ev["features"]; d = ev["decision"]
    actor = ("an automated client (not the genuine app)" if d["human_likeness"] < .4 else
             "a genuine customer who may be under coercion" if d.get("coercion_like") else "an account operated by someone other than the usual user")
    return (f"Session {ev['session_id']} for user {ev['user_id']} reached a risk score of {ev['score']:.2f} after {ev['n_events']} events. "
            f"Top drivers: {', '.join(ev['top_reasons'][:3])}. The traffic pattern suggests {actor} "
            f"(human-likeness {d['human_likeness']}). Recommended: {d['tier'].replace('_', ' ')} — {d['rationale']}")


def narrative(ev: dict) -> dict:
    out = {"source": "template", "model": None}
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(model=MODEL, max_tokens=300, system=SYSTEM,
                                         messages=[{"role": "user", "content": "EVIDENCE_JSON:\n" + json.dumps(ev, default=str)}])
            out.update(source="llm", model=MODEL, text=msg.content[0].text)
            return out
        except Exception as e:
            out["error"] = str(e)[:200]
    out["text"] = template(ev)
    return out
