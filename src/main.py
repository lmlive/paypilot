# PayPilot — AI payment approval agent for PayPal
# 4-agent desk (Scout → Estimator → Decision → Risk) → PayPal Payouts API
# Built for PayPal AI Hackathon 2026 ($69,750 total prize pool)

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from paypal_client import PayPalClient  # noqa: E402
from agents import AgentTeam  # noqa: E402

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_PAYOUT = float(os.getenv("MAX_PAYOUT_USDC", "50.0"))
MIN_CONF = float(os.getenv("MIN_CONFIDENCE", "0.6"))


def log(obj: dict):
    obj["ts"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def need(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if not v:
        print(f"Missing required env var: {name} "
              f"(copy .env.example to .env and fill it in)")
        sys.exit(2)
    return v


def main():
    if len(sys.argv) < 2:
        print('Usage: python main.py \'<json payment request>\'')
        print('Example: python main.py \'{"payee":"freelancer@example.com",'
              ' "amount":25.0, "currency":"USD",'
              ' "description":"Logo design milestone 2 approved"}\'')
        sys.exit(1)

    request = json.loads(sys.argv[1])
    team = AgentTeam(need("LLM_BASE_URL"), os.environ.get("LLM_API_KEY", ""),
                     os.environ.get("LLM_MODEL", "cohere/north-mini-code:free"))
    result = team.review(request, MAX_PAYOUT, MIN_CONF)
    log({"event": "review", **result})

    if result["decision"] == "APPROVE" and result["confidence"] >= MIN_CONF:
        amount = min(result["amount"], MAX_PAYOUT)
        if DRY_RUN:
            log({"event": "payout_dry_run", "payee": request.get("payee"),
                 "amount": amount, "note": "no real payout in DRY_RUN"})
            return
        pp = PayPalClient(need("PAYPAL_BASE_URL"),
                          need("PAYPAL_CLIENT_ID"),
                          need("PAYPAL_CLIENT_SECRET"))
        payout = pp.create_payout(request["payee"], f"{amount:.2f}",
                                  request.get("currency", "USD"),
                                  result.get("reason", ""))
        log({"event": "payout_done",
             "batch_id": payout.get("batch_header", {}).get("payout_batch_id")})
    else:
        log({"event": "held", "reason": result.get("reason")})


if __name__ == "__main__":
    main()
