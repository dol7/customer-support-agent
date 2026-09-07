"""The coordinator.

Host-orchestrated, because Agent-tool subagents on the SDK are deferred and do
not complete inside the spawning turn. The coordinator here is: an LLM
decomposition, deterministic routing of each concern to a specialist, running
each specialist as its own scoped ``run_agent`` call, a coverage check against
the ticket, and an LLM report.

Every specialist call is an ``AgentDefinition`` with its own ``tools`` list; the
hook runs on every one of them; a concern the decomposition never produced is a
gap the coverage check re-delegates.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from .agents import AGENTS
from .backend import TICKET_CONCERNS
from .config import MAX_COVERAGE_ROUNDS, TODAY
from .findings import coverage_gaps
from .prompts import DECOMPOSE_PROMPT, GOAL_SYSTEM, REPORT_PROMPT
from .session import Metrics, RunResult, run_agent, run_plain
from .tools import get_customer

_INVESTIGATE = "order-investigator"
_POLICY = "policy-analyst"
_REFUND = "refund-processor"
_ESCALATE = "escalation-writer"


@dataclass
class Resolution:
    concerns: list[dict]
    findings: list[dict]
    gaps: list[dict]
    rounds: list[dict]
    report: str
    metrics: Metrics = field(default_factory=Metrics)


def _parse_concern_lines(text: str) -> list[dict]:
    out, seen = [], set()
    for m in re.finditer(r"(?mi)^\s*[-*#>\s]*\**\s*(c\d+)\**\s*[:.\)-]\s*(.+?)\s*$", text):
        cid = m.group(1).lower()
        if cid not in seen:
            seen.add(cid)
            out.append({"id": cid, "detail": m.group(2).strip().strip("*").strip()})
    return out


def map_to_ticket(coord_concern: dict) -> str | None:
    """Which ticket concern (c1..c4) this coordinator-decomposition item is
    about — by content, not by the id the coordinator happened to give it. A
    narrow coordinator that never mentions the chargeback threat maps nothing to
    c4, so c4 shows up as a coverage gap."""
    d = coord_concern.get("detail", "").lower()
    for tc in TICKET_CONCERNS:
        oid = tc.get("order_id")
        if oid and oid.lower() in d:
            return tc["id"]
    if any(w in d for w in ("chargeback", "escalat", "file a charge", "threat", "dispute")):
        return "c4"
    if any(w in d for w in ("return window", "still return", "returnable", "45 day", "return policy")):
        return "c3"
    return None  # e.g. "verify the customer" — real work, but not a ticket concern


def route(concern: dict) -> list[str]:
    """Which specialist(s) this concern needs. Rule-based and deterministic —
    routing by what the concern is, not by an LLM guess."""
    d = (concern.get("detail", "") + " " + concern.get("kind", "")).lower()
    if any(w in d for w in ("chargeback", "lawyer", "bbb", "social media", "threat", "escalat")):
        return [_ESCALATE]
    if any(w in d for w in ("return window", "still return", "can i return", "policy", "window")):
        return [_POLICY]
    if any(w in d for w in ("charged twice", "double charge", "duplicate", "billing", "refund", "damaged", "damage")):
        return [_INVESTIGATE, _REFUND]
    return [_INVESTIGATE]


async def _customer(fault: str | None) -> dict:
    raw = await get_customer.handler({"email": "alice@example.com"})
    return json.loads(raw["content"][0]["text"])


async def _handle(concern: dict, cust: dict, *, fault: str | None,
                  metrics: Metrics, on_event: Callable | None) -> list[dict]:
    cid = concern["id"]
    plan = route(concern)
    findings: list[dict] = []

    if on_event:
        on_event("note", {"text": f"{cid} -> {plan}  ({concern['detail']})"})

    order_id = _order_ref(concern["detail"]) or _ticket_order(cid) or "ORD-000"
    inv: RunResult | None = None

    if _INVESTIGATE in plan:
        inv = await run_agent(
            AGENTS[_INVESTIGATE],
            f"Concern {cid}. Look up order {order_id}. Customer {cust['customer_id']} "
            f"({cust['name']}), verified. Today {TODAY}. The customer says: "
            f"\"{concern['detail']}\". Report every field and whether the claim holds.",
            metrics=metrics, fault=fault, on_event=on_event, label=f"{cid}/{_INVESTIGATE}",
        )
        findings += _tag(inv.findings, cid)

    # A structured transient failure: the coordinator stops the refund for this
    # concern, records what it knows, and moves on. c2 stays named as unresolved.
    if inv is not None and _investigation_failed(inv.text):
        if on_event:
            on_event("note", {"text": f"{cid}: investigation returned a transient failure — "
                                      "holding the refund, proceeding on the other concerns"})
        findings.append({
            "concern_id": cid,
            "claim": f"{cid} left unresolved — the {order_id} lookup could not run",
            "evidence": _first_line(inv.text),
            "source": f"lookup_order({order_id}) — transient failure, retryable",
        })
        return findings

    if _REFUND in plan:
        amount, kind = _refund_amount(concern["detail"], inv.text if inv else "")
        r = await run_agent(
            AGENTS[_REFUND],
            f"Concern {cid}. Issue a refund against order {order_id} for {amount:.2f}. "
            f"Reason: {kind}. Customer {cust['customer_id']} ({cust['name']}), verified. "
            f"The order was investigated: {_inv_summary(inv)}. Today {TODAY}.",
            metrics=metrics, fault=fault, on_event=on_event, label=f"{cid}/{_REFUND}",
        )
        findings += _tag(r.findings, cid)
        if _denied(r.text):
            e = await run_agent(
                AGENTS[_ESCALATE],
                f"Concern {cid}. A refund of {amount:.2f} on {order_id} was denied by the "
                f"$500 ceiling and needs Tier 2 approval. Customer {cust['customer_id']} "
                f"({cust['name']}). root_cause: {concern['detail']}; refund over the auto "
                f"limit. recommended_action: Tier 2 review and approve the {amount:.2f} refund.",
                metrics=metrics, fault=fault, on_event=on_event, label=f"{cid}/{_ESCALATE}",
            )
            findings += _tag(e.findings, cid)

    if _POLICY in plan:
        order = _order_facts(order_id)
        p = await run_agent(
            AGENTS[_POLICY],
            f"Concern {cid}. Question: {concern['detail']} Facts: order {order_id}, "
            f"item {order.get('sku')} ({_category(order.get('sku',''))}), delivered "
            f"{order.get('delivered_on')}, today {TODAY}, condition {order.get('condition')}, "
            f"amount {order.get('amount')}. Cite the clause and answer.",
            metrics=metrics, fault=fault, on_event=on_event, label=f"{cid}/{_POLICY}",
        )
        findings += _tag(p.findings, cid)

    if _ESCALATE in plan and _REFUND not in plan:
        e = await run_agent(
            AGENTS[_ESCALATE],
            f"Concern {cid}. {concern['detail']} Customer {cust['customer_id']} "
            f"({cust['name']}), email {cust['email']}. root_cause: {concern['detail']} "
            f"recommended_action: a human agent must review and respond today, per the "
            f"escalation policy on chargeback threats (clause 3.4).",
            metrics=metrics, fault=fault, on_event=on_event, label=f"{cid}/{_ESCALATE}",
        )
        findings += _tag(e.findings, cid)

    if not findings:
        findings = [{"concern_id": cid, "claim": "no specialist produced a finding",
                     "evidence": "empty", "source": f"route={plan}"}]
    return findings


async def resolve(
    ticket: str,
    *,
    today: str = TODAY,
    coordinator_system: str = GOAL_SYSTEM,
    fault: str | None = None,
    on_event: Callable | None = None,
    max_rounds: int = MAX_COVERAGE_ROUNDS,
) -> Resolution:
    metrics = Metrics()
    cust = await _customer(fault)

    d = await run_plain(coordinator_system, DECOMPOSE_PROMPT.format(ticket=ticket),
                        metrics=metrics, on_event=on_event, label="decompose")
    concerns = _parse_concern_lines(d.text)

    # Map the coordinator's decomposition onto the ticket. Ticket concerns that
    # nothing maps to are round-1 gaps — the "before" half of the coverage demo.
    mapped = {tid for c in concerns if (tid := map_to_ticket(c))}
    by_id = {c["id"]: c for c in TICKET_CONCERNS}
    todo = [by_id[t] for t in ("c1", "c2", "c3", "c4") if t in mapped]
    if on_event:
        on_event("note", {"text": f"coordinator named {len(concerns)} items; they map to "
                                  f"ticket concerns {sorted(mapped)} "
                                  f"(unmapped: {sorted(set(by_id) - mapped) or 'none'})"})

    findings: list[dict] = []
    rounds: list[dict] = []

    for rnd in range(1, max_rounds + 1):
        for c in todo:
            findings += await _handle(c, cust, fault=fault, metrics=metrics, on_event=on_event)
        gaps = coverage_gaps(TICKET_CONCERNS, findings)
        rounds.append({"round": rnd, "delegated": [c["id"] for c in todo],
                       "covered_after": sorted({f["concern_id"] for f in findings}),
                       "gaps_after": [g["id"] for g in gaps]})
        if on_event:
            on_event("note", {"text": f"round {rnd}: delegated {[c['id'] for c in todo]} -> "
                                      f"covered {rounds[-1]['covered_after']}, gaps {rounds[-1]['gaps_after']}"})
        if not gaps:
            break
        todo = gaps

    gaps = coverage_gaps(TICKET_CONCERNS, findings)
    rep = await run_plain(
        coordinator_system,
        "Findings from the specialists:\n" + json.dumps(findings, indent=2) + "\n\n"
        + REPORT_PROMPT.format(ids=", ".join(c["id"] for c in TICKET_CONCERNS)),
        metrics=metrics, on_event=on_event, label="report",
    )
    return Resolution(concerns=concerns, findings=findings, gaps=gaps,
                      rounds=rounds, report=rep.text, metrics=metrics)


# --- small helpers ----------------------------------------------------------------
def _tag(fs: list[dict], cid: str) -> list[dict]:
    for f in fs:
        f["concern_id"] = cid
    return fs


def _order_ref(text: str) -> str | None:
    m = re.search(r"ORD-\d+", text.upper())
    return m.group(0) if m else None


def _ticket_order(cid: str) -> str | None:
    for c in TICKET_CONCERNS:
        if c["id"] == cid:
            return c.get("order_id")
    return None


def _order_facts(order_id: str) -> dict:
    from .backend import ORDERS
    return ORDERS.get(order_id, {})


def _category(sku: str) -> str:
    return {"FW": "footwear", "AP": "apparel", "EL": "electronics"}.get(sku[:2], "general")


def _inv_summary(inv: RunResult | None) -> str:
    return (inv.text[:300] if inv and inv.text else "not investigated")


def _refund_amount(detail: str, inv_text: str) -> tuple[float, str]:
    d = detail.lower()
    order_id = _order_ref(detail)
    facts = _order_facts(order_id)
    amt = float(facts.get("amount", 0) or 0)
    if any(w in d for w in ("charged twice", "double", "duplicate")):
        return amt, "billing_error"        # refund the one duplicate charge
    return amt, "damaged"


def _denied(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ("denied", "ceiling", "tier 2", "over the", "not approved"))


def _investigation_failed(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in (
        "lookup failed", '"transient"', "timed out", "could not run",
        '"iserror": true', "order service", "errorcategory",
    ))


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0][:400] if text.strip() else "(no detail)"
