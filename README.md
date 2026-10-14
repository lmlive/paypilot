# PayPilot — AI Payment Approval Agent

Autonomous 4-agent desk that reviews payment requests and executes approved
payouts via PayPal. Built for the **PayPal AI Hackathon 2026** ($69,750 total prize pool).

**Powered by PayPal** · MIT

## The problem

Freelancers, contractors, and vendors submit payment requests constantly.
Someone has to check: is this legitimate? Does the amount match the work?
Is the payee who they claim to be? Manual review doesn't scale; rubber-stamping
invites fraud.

## The solution

PayPilot runs every payment request through a 4-agent pipeline before a cent moves:

```
[ 🔍 Scout ] → [ 📊 Estimator ] → [ 🎯 Decision ] → [ 🛡️ Risk ] → [ 💸 PayPal Payout ]
  Extract facts   Legitimacy score   Approve / Hold    Veto power    Payouts API
```

Only verified consensus triggers a real PayPal payout. Everything else is held
for human review — with the full evidence chain logged.

## PayPal integration

| API | Use |
|---|---|
| `POST /v1/oauth2/token` | OAuth2 client-credentials auth |
| `POST /v1/payments/payouts` | Batch payout to payee email |
| `GET /v1/payments/payouts/{id}` | Payout status tracking |

Sandbox: `https://api-m.sandbox.paypal.com` (no real money moves).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add PAYPAL_CLIENT_ID/SECRET, LLM_API_KEY
# DRY_RUN=true by default — reviews without paying

python src/main.py '{"payee":"freelancer@example.com","amount":25.0,"currency":"USD","description":"Logo design milestone 2 approved by reviewer"}'
```

## Safety

- `DRY_RUN=true` default: reviews and logs, never pays
- `MAX_PAYOUT_USDC` per-payment cap (default 50)
- `MIN_CONFIDENCE` threshold (default 0.6)
- Risk agent holds absolute veto

## Architecture

```
src/paypal_client.py  # PayPal Sandbox REST (OAuth + Payouts)
src/agents.py         # 4-agent LLM pipeline
src/main.py           # CLI entry: review one payment request
```
