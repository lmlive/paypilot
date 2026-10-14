"""4-agent payment approval team: Scout → Estimator → Decision → Risk.

Adapted from PantaPilot's trading desk for PayPal agentic commerce.
Each role is a dedicated LLM call; any failure degrades gracefully.
"""
from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

log = logging.getLogger("paypilot.agents")

for _k in ("no_proxy", "NO_PROXY"):
    _v = os.environ.get(_k, "")
    if "[" in _v:
        os.environ[_k] = ",".join(p for p in _v.split(",") if "[" not in p)


SCOUT_PROMPT = """You are a payment intake scout. Given a payment request
(payee, amount, description, any attached invoice text), extract and
normalize the key facts. Flag anything missing or suspicious
(e.g. no description, round-number amount with no justification,
payee never seen before).

Output ONLY JSON:
{"payee": "...", "amount": 0.0, "currency": "...", "description": "...",
 "flags": ["..."], "completeness": "low|medium|high"}"""

ESTIMATOR_PROMPT = """You are a payment legitimacy estimator. Given the scout's
fact sheet, estimate how likely this payment is legitimate and appropriate
(0-1). Consider: does the amount match the described work? Is the payee
plausible? Are there red flags?

Output ONLY JSON:
{"legitimacy": 0.0, "confidence": 0.0,
 "key_evidence": "1-3 bullet points", "uncertainty": "low|medium|high"}"""

DECISION_PROMPT = """You are a disciplined payment approver. You receive the
scout's facts and the estimator's legitimacy score.

Approve ONLY when: legitimacy >= 0.7, no unresolved red flags, amount is
within the payer's typical range.
Otherwise HOLD.

Output ONLY JSON:
{"decision": "APPROVE"|"HOLD", "confidence": 0.0,
 "reason": "short reason", "amount": 0.0}"""

RISK_PROMPT = """You are a risk manager with veto power over a proposed payment.

Veto (final = HOLD) if: confidence below threshold, amount exceeds the cap,
payee is new AND amount is large, or rationale is weak.

Output ONLY JSON:
{"final": "APPROVE"|"HOLD", "approved": true|false, "note": "short reason"}"""


def _parse_json(content: str) -> dict | None:
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except Exception:
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(content[s:e + 1])
            except Exception:
                return None
        return None


class AgentTeam:
    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 60.0):
        self.model = model
        self.enabled = bool(api_key)
        self.client = OpenAI(base_url=base_url, api_key=api_key or "sk-dummy",
                             timeout=timeout, max_retries=1)

    def _ask(self, system: str, user: str) -> dict | None:
        if not self.enabled:
            return None
        try:
            r = self.client.chat.completions.create(
                model=self.model, temperature=0.2,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            return _parse_json(r.choices[0].message.content or "")
        except Exception as e:
            log.warning("agent call failed: %s", e)
            return None

    def review(self, request: dict, max_amount: float,
               min_confidence: float) -> dict:
        """Full pipeline. request: {payee, amount, currency, description}."""
        req_text = json.dumps(request, ensure_ascii=False)

        scout = self._ask(SCOUT_PROMPT, req_text)
        if not scout:
            return {"decision": "HOLD", "confidence": 0,
                    "reason": "scout failed", "amount": 0,
                    "pipeline": "scout_failed"}

        est = self._ask(ESTIMATOR_PROMPT, json.dumps(scout, ensure_ascii=False))
        dec_input = {"scout": scout, "estimator": est}
        dec = self._ask(DECISION_PROMPT, json.dumps(dec_input, ensure_ascii=False))
        if not dec:
            return {"decision": "HOLD", "confidence": 0,
                    "reason": "decision failed", "amount": 0,
                    "pipeline": "decision_failed",
                    "evidence": {"scout": scout, "estimator": est}}

        decision = str(dec.get("decision", "HOLD")).upper()
        if decision not in ("APPROVE", "HOLD"):
            decision = "HOLD"
        try:
            conf = max(0.0, min(1.0, float(dec.get("confidence", 0))))
        except Exception:
            conf = 0.0
        try:
            amount = max(0.0, float(dec.get("amount", 0)))
        except Exception:
            amount = 0.0

        risk = self._ask(RISK_PROMPT, json.dumps({
            "proposal": {"decision": decision, "confidence": conf, "amount": amount},
            "estimator": est,
            "max_amount": max_amount,
            "min_confidence": min_confidence,
        }, ensure_ascii=False))
        if risk and not risk.get("approved", True):
            return {"decision": "HOLD", "confidence": min(conf, 0.5),
                    "reason": f"[risk veto] {risk.get('note', '')}",
                    "amount": 0, "pipeline": "scout>estimator>decision>risk(veto)",
                    "evidence": {"scout": scout, "estimator": est, "risk": risk}}

        if conf < min_confidence or amount > max_amount or amount <= 0:
            decision = "HOLD"

        return {"decision": decision, "confidence": conf,
                "reason": dec.get("reason", ""), "amount": amount,
                "pipeline": "scout>estimator>decision>risk",
                "evidence": {"scout": scout, "estimator": est, "risk": risk}}
