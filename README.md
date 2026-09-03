# Customer Support Resolution Agent

A customer-support agent for a mid-size e-commerce retailer — returns, billing disputes,
account issues. It reaches the backend through **Messages API tool definitions** (`name`,
`description`, `input_schema` — the three MCP-shaped fields, but there is no MCP server) and a
**hand-written agentic loop**. Target: resolve ~80% of contacts on first contact, escalate the
rest with a ticket a human can act on.

## Three rules, and where each one lives

| Rule | Enforced by | Not in |
|---|---|---|
| No order operation before identity is verified | `tools._identity_gate` (pre-exec hook in `dispatch`) | the system prompt |
| Refunds above **$500** need a human | `backend.REFUND_AUTO_APPROVAL_LIMIT`, checked in `tools._ceiling_check` **and** `tools._process_refund` | the system prompt |
| An explicit request for a human is honoured immediately | the system prompt + `escalate_to_human` | — |

The literal `500` appears in exactly one file: [`src/support_agent/backend.py`](src/support_agent/backend.py).
The system prompt ([`system_prompt.py`](src/support_agent/system_prompt.py)) never states the
identity rule or the ceiling. `tests/test_enforcement.py::test_gates_hold_under_hostile_system_prompt`
replays the loop under a prompt that orders the model to skip both rules; the gates still hold,
because the tool layer does not read a prompt.

## The four tools

| Tool | Does | Key precondition |
|---|---|---|
| `get_customer` | Verify a person from **email or phone + name**; returns the `customer_id` everything else needs | — |
| `lookup_order` | Read one order's status / items / totals / refund-eligibility, **by order number** | session verified |
| `process_refund` | Issue a refund (moves money) | session verified, amount ≤ $500 |
| `escalate_to_human` | Open a self-contained ticket (customer + order snapshot + reason) | — |

`get_customer` and `lookup_order` are close enough to misroute. The fix is in the descriptions
(no few-shot, no router): each names its **lookup key** (person identifiers vs. an order
number), its **precondition** (verification), its **output shape**, and a **"when NOT to use"**
list that points at the sibling. See [`tools.py`](src/support_agent/tools.py).

## The loop

[`agent.py`](src/support_agent/agent.py) branches on `response.stop_reason`:

- `tool_use` → run **every** `tool_use` block, append **one** user message containing all the
  `tool_result` blocks (each with its matching `tool_use_id`), continue.
- `end_turn` → done. **This is the primary termination** — no natural-language parsing of the
  reply to decide when to stop.
- `max_tokens` → **raise** `MaxTokensError`.
- anything else (`refusal`, …) → **raise** `UnexpectedStopReason`.

The iteration counter (`max_iterations`, default 10) is a **labelled safety net**
(`LoopSafetyCapExceeded`), not the termination mechanism — a healthy conversation returns on
`end_turn` well before it trips.

## Structured errors & lean payloads

Tools **never raise into the loop**. A tool that can't do its job returns
`{ "ok": false, "errorCategory", "isRetryable", "message" }`:

| category | isRetryable | agent behaviour |
|---|---|---|
| `transient` | `true` | retry as-is |
| `validation` | `true` | fix the argument, retry |
| `business` | `false` | explain to the customer in plain language (`message` is customer-safe) |
| `permission` | `false` | do **not** retry — escalate |

`--fail-mode {transient,validation,business,permission}` injects one deterministic failure so a
single run exercises a category. `business` and `permission` also arise naturally from the seed
data (ORD-456 is 74 days delivered and totals $742).

Result payloads carry only what Claude needs on later turns — order status, `refundable_amount`,
currency, item name/qty, the verified `customer_id`. Stripped: SKUs, internal row ids, epoch
timestamps, gateway responses, address, payment instrument, any `_debug`/metadata. Asserted in
`tests/test_errors.py::test_payloads_are_lean_no_debug_padding`.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # or: pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # ANTHROPIC_MODEL defaults to claude-opus-5

# one message, two jobs, one reply
support-agent "Hi, this is Alice Nguyen (alice.nguyen@example.com). Refund ORD-123 — cracked jug — and where is ORD-789?"

# business error: agent explains, does not retry
support-agent --fail-mode business "Bob Carter, bob.carter@example.com — refund ORD-456"

# explicit human request
support-agent "I want to talk to a person about ORD-456"
```

Docker (mirrors the bootcamp's `week1-fastapi-intro` image):

```bash
docker build -t maven-claude-cert .
docker run --rm -e ANTHROPIC_API_KEY -e ANTHROPIC_MODEL maven-claude-cert "status of ORD-789 for Alice Nguyen, alice.nguyen@example.com"
```

Tests (no API key, no network — a scripted fake client drives the loop):

```bash
pytest -q
```

## Transcripts

`python scripts/capture_transcripts.py` runs the scenarios against the real API and writes
`transcripts/*.md` + `.json` (committed copies are in [`transcripts/`](transcripts/)):

| scenario | shows |
|---|---|
| `happy_path_alice` | one message, two jobs (refund ORD-123 + status of ORD-789), answered in a single reply |
| `escalation_bob` | explicit "put me through to a person" → self-contained ticket (customer + order snapshot + reason) |
| `ceiling_escalation` | `process_refund` $680 on ORD-555 → the **$500 code ceiling** returns a `permission` error → agent escalates, does not retry |
| `error_transient` | order service times out once → agent retries → succeeds |
| `error_business` | `--fail-mode business` → non-retryable, customer-facing explanation; no retry |
| `error_validation` | `--fail-mode validation` → retryable → agent retries and the refund goes through |

## Noticing misrouting in production

`scripts/routing_eval.py` is an offline probe. In production, log
`(first_tool_called, escalation_category, resolved?)` per conversation and watch for:

- `get_customer` ↔ `lookup_order` called back-to-back on the same turn pair (model corrected itself),
- an `identity not verified` permission error immediately after a `lookup_order` attempt,
- a rising *first-tool-corrected* rate.

---

## Reflection

### 1. You put the refund ceiling in code. Argue for a system-prompt instruction instead, then explain why it loses.

**The case for the prompt.** It's one sentence — "never refund more than $500 without a
human." No deploy, no code review, no test. Policy can change with a prompt edit. It keeps
business logic in the place non-engineers can read and adjust, and it lets the model apply
judgement at the margin (a $505 refund to a furious 10-year customer) instead of hitting a wall
at a hard number.

**Why it loses.** A prompt instruction is followed *probabilistically*. A code gate is followed
*always*. That difference is the whole argument, and it shows up as money.

- **Failure rate.** Even a well-behaved model doesn't comply 100% of the time on every phrasing.
  Call it a 1–3% slip rate on adversarial or confusing inputs — split refunds ("refund $300 now
  and $300 tomorrow"), currency ambiguity, a customer who says "your system already approved
  this", or a prompt-injection string that arrives *inside a tool result* and tells the model
  the limit was lifted. The rate isn't fixed; it drifts with model version, temperature, and
  context length, and you find out it moved by reading a refund report.
- **Money.** A mid-size retailer runs, say, 3,000 disputed contacts a month. If 15% touch a
  refund near or above the line and the model slips 2% of those, that's ~9 over-limit refunds a
  month that should have had a human. At a few hundred dollars over the line each, that's low
  thousands of dollars a month leaking, every month, with no consistent audit trail and no
  single place to point an auditor.
- **The requirement is absolute, so the control should be too.** "Needs human approval above
  $500" is a controls statement, not a preference. `tools._ceiling_check` is one line, one
  enforcement point, unit-tested (`test_ceiling_blocks_refund_above_limit_and_moves_no_money`),
  and provably 0% slip. The prompt still carries the *soft* guidance ("escalate when you can't
  finish"); the hard number lives where it can't be argued with.

### 2. Your two similar tools — what did you write so Claude can tell them apart, and how would you notice misrouting in production?

Both tools "look something up about the customer," so a thin description ("get customer info" /
"get order info") gets them confused. Each description now carries four things:

1. **Its lookup key.** `get_customer` is keyed by *personal identifiers* (email/phone + name)
   and explicitly "cannot look someone up from an order number." `lookup_order` is keyed by
   *the order number* and "assumes identity is already established."
2. **Its precondition.** `lookup_order` and `process_refund` say "session must already be
   verified — pass the `customer_id` from `get_customer`." `get_customer` says "don't verify
   again if you already did."
3. **Its output shape**, field by field, so the model can check whether this is the tool that
   returns the thing it needs.
4. **A "when NOT to use" list that names the sibling.** `get_customer` → "if you want order
   status/items/totals, that's `lookup_order`." `lookup_order` → "to identify or verify the
   customer, that's `get_customer`." Plus the awkward case spelled out: order number and no
   email/phone → you *can't* verify from an order number, ask for an identifier.

**Noticing it in production.** Log per conversation: the first tool called, whether the next
turn immediately called a different tool (self-correction), any permission error that landed
right after a `lookup_order` attempt (model tried to read an order before verifying), and the
eventual resolution. Alert on a rising *first-tool-corrected* rate or a spike in
"identity not verified" errors — both mean the descriptions have drifted out of sync with how
customers actually phrase things, or a new model reads them differently. `scripts/routing_eval.py`
is the same check run offline against a fixed probe set before a model bump.

### 3. Every tool_result is resent on later turns. What did you strip from payloads, and what would break if a summary dropped the refund amount?

**Stripped:** SKUs, internal row/customer database ids, epoch timestamps (kept human ISO
strings only where a date matters), payment-gateway raw responses, billing address, payment
instrument, pagination cursors, and anything shaped like `_debug` / `_meta` / `trace`. A
`lookup_order` result is ~10 fields plus a trimmed items list of `{name, qty, unit_price}` —
enough to discuss the order and reason about a refund, nothing more. This is asserted, not
aspirational (`test_payloads_are_lean_no_debug_padding`).

**If a summary dropped the refund amount** — say a context-compaction step rewrote
`{"ok": true, "refund_id": "RF-…", "amount": "165.00", …}` down to "refund processed" — later
turns lose the one number three different things depend on:

- **The rules can't be checked.** The next `process_refund` (a second partial refund, a
  correction) needs the prior `amount` to know what's left against `refundable_amount`, and the
  ceiling check compares against `$500`. Without it the model either refuses to act or guesses.
- **The customer gets a wrong or vague answer.** "I've refunded your order" instead of "I've
  refunded $165.00" — and if the customer disputes the figure, the agent has nothing to stand
  on and will hallucinate a number to fill the gap.
- **The escalation ticket becomes non-actionable.** If the case later escalates, the ticket's
  `reason` should say "refunded $165.00, customer wants the remaining $18.00 for the spare
  cup." Drop the amount and the human gets "customer wants a refund" with no figure — exactly
  the "escalating…" ticket the rubric calls insufficient.

The amount is load-bearing state, so it stays in the payload verbatim as a decimal string —
never folded into prose, never summarised away.
