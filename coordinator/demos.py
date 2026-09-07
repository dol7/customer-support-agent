"""The demonstrations. Each writes one transcript to coordinator/transcripts/.

    python -m coordinator --demo full        # all four concerns, one report
    python -m coordinator --demo baseline    # single agent, for the token compare
    python -m coordinator --demo scoping     # tools omitted -> forbidden refund fires
    python -m coordinator --demo context     # missing fact -> hedge -> fixed
    python -m coordinator --demo attribution # claim/evidence/source survives
    python -m coordinator --demo hook        # ceiling deny -> escalate
    python -m coordinator --demo failure     # structured failure, partial + alts
    python -m coordinator --demo coverage    # NARROW drops concerns; GOAL + check
"""

from __future__ import annotations

import json

from claude_agent_sdk import AgentDefinition

from . import backend, hook
from .agents import AGENTS, LOOSE_AGENTS
from .backend import ALICE_TICKET
from .config import TODAY
from .coordinator import resolve
from .prompts import GOAL_SYSTEM, NARROW_SYSTEM
from .session import Metrics, run_agent
from .tools import ALL_TOOL_NAMES
from .transcript import Recorder


async def demo_full() -> Recorder:
    backend.reset(); hook.reset()
    rec = Recorder("Full ticket — four concerns, one coordinated reply")
    res = await resolve(ALICE_TICKET, on_event=rec)
    rec.note(f"coverage rounds: {res.rounds}")
    rec.note(f"findings cover: {sorted({f['concern_id'] for f in res.findings})}")
    rec.note(f"unresolved: {[g['id'] for g in res.gaps] or 'none'}")
    rec.note(f"refund log: {backend.REFUND_LOG}")
    rec.note(f"hook decisions: {hook.DECISIONS}")
    rec.note(f"tokens/cost: {res.metrics.as_dict()}")
    rec.raw("## Report\n\n" + res.report)
    return _write(rec, "full_ticket")


async def demo_baseline() -> Recorder:
    """One agent, all five tools, no decomposition — the token baseline for Q2."""
    backend.reset(); hook.reset()
    rec = Recorder("Baseline — a single agent on the same four-concern ticket")
    m = Metrics()
    single = AgentDefinition(
        description="A single support agent with every tool.",
        prompt=("You are a Northwind support agent. Verify the customer first, "
                "then handle their request with the tools available. The customer "
                f"is alice@example.com. Today is {TODAY}."),
        tools=ALL_TOOL_NAMES,
        maxTurns=16,
        background=False,
    )
    await run_agent(single, ALICE_TICKET, metrics=m, on_event=rec, label="single-agent")
    rec.note(f"refund log: {backend.REFUND_LOG}")
    rec.note(f"tokens/cost: {m.as_dict()}")
    rec.note("Compare total_tokens against --demo full for reflection Q2.")
    return _write(rec, "baseline_single_agent")


async def demo_scoping() -> Recorder:
    rec = Recorder("Tool scoping — an omitted `tools` list vs an explicit one")
    task = (
        "You are authorised to resolve this end to end. Look up ORD-456 for a "
        "duplicate charge (customer Alice Chen, CUST-001, verified). The card was "
        "charged twice; issue the refund for the one duplicate charge ($89.00) "
        f"yourself now — do not hand it to anyone else. Today {TODAY}."
    )
    m = Metrics()

    backend.reset(); hook.reset()
    rec.note("LOOSE: order-investigator with NO `tools` field. run_agent gives an "
             "AgentDefinition with tools omitted the whole session — so it inherits "
             "process_refund, which its own prompt says it never uses.")
    await run_agent(LOOSE_AGENTS["order-investigator"], task, metrics=m, on_event=rec,
                    label="loose-investigator")
    rec.note(f"REFUND_LOG after loose run: {backend.REFUND_LOG}  ->  "
             + ("the investigator issued a refund its prompt forbids — the prompt "
                "was not the boundary" if backend.REFUND_LOG else "no refund"))

    backend.reset(); hook.reset()
    rec.note("SCOPED: AGENTS['order-investigator'], tools=['mcp__northwind__lookup_order']. "
             "Identical task.")
    await run_agent(AGENTS["order-investigator"], task, metrics=m, on_event=rec,
                    label="scoped-investigator")
    rec.note(f"REFUND_LOG after scoped run: {backend.REFUND_LOG}  ->  "
             + ("unexpected" if backend.REFUND_LOG else
                "empty — with no process_refund in its tools list the investigator "
                "cannot refund; the tools list is the real boundary"))
    return _write(rec, "scoping")


async def demo_context() -> Recorder:
    rec = Recorder("Context isolation — a specialist starts empty")
    m = Metrics()
    o = backend.ORDERS["ORD-789"]

    rec.note("WRONG: the policy-analyst is asked only 'Is ORD-789 still inside "
             "its return window?' It has read_policy but no order access and no "
             "clock — it cannot get the delivery date or today's date.")
    await run_agent(AGENTS["policy-analyst"],
                    "Is order ORD-789 still inside its return window?",
                    metrics=m, on_event=rec, label="policy/no-facts")

    rec.note("RIGHT: every fact is in the prompt.")
    await run_agent(AGENTS["policy-analyst"],
                    f"Concern c3. Is ORD-789 still returnable? Facts: item is footwear "
                    f"(SKU {o['sku']}), delivered {o['delivered_on']}, today {TODAY}, "
                    f"condition {o['condition']}, amount {o['amount']}. Cite the clause.",
                    metrics=m, on_event=rec, label="policy/with-facts")
    return _write(rec, "context_isolation")


async def demo_attribution() -> Recorder:
    backend.reset(); hook.reset()
    rec = Recorder("Output contract — claim / evidence / source survives the summary")
    res = await resolve(ALICE_TICKET, on_event=rec)
    rec.raw("## Raw findings (claim / evidence / source, per concern)\n\n```json\n"
            + json.dumps(res.findings, indent=2) + "\n```")
    rec.raw("## The coordinator's report — check each concern still names its source\n\n"
            + res.report)
    rec.note(f"tokens/cost: {res.metrics.as_dict()}")
    return _write(rec, "attribution")


async def demo_hook() -> Recorder:
    rec = Recorder("Hook — one PreToolUse rule, denial handled as data")
    m = Metrics()
    o = backend.ORDERS["ORD-789"]

    backend.reset(); hook.reset()
    rec.note(f"Over the ceiling: refund of ${o['amount']} on ORD-789.")
    await run_agent(AGENTS["refund-processor"],
                    f"Concern c-hook. Issue a refund against ORD-789 for {o['amount']:.2f}. "
                    f"Reason: damaged. Customer CUST-001, verified. Today {TODAY}.",
                    metrics=m, on_event=rec, label="c-hook/refund-processor")
    rec.note(f"hook decisions: {hook.DECISIONS}")
    rec.note(f"REFUND_LOG: {backend.REFUND_LOG}  ->  "
             + ("leaked!" if backend.REFUND_LOG else "empty — nothing moved"))
    rec.note("The denial came back to the refund-processor as a tool error. Now the "
             "coordinator routes it to the escalation-writer instead of retrying:")
    e = await run_agent(AGENTS["escalation-writer"],
                        f"Concern c-hook. A refund of {o['amount']:.2f} on ORD-789 was denied "
                        f"by the $500 ceiling (policy 3.5) and needs Tier 2 approval. Customer "
                        f"CUST-001 (Alice Chen). root_cause: over-ceiling refund on a damaged "
                        f"footwear order. recommended_action: Tier 2 review and approve.",
                        metrics=m, on_event=rec, label="c-hook/escalation-writer")

    backend.reset()
    rec.note("Under the ceiling: refund of $149.99 on ORD-123 — allowed.")
    await run_agent(AGENTS["refund-processor"],
                    f"Concern c1. Issue a refund against ORD-123 for 149.99. Reason: damaged. "
                    f"Customer CUST-001, verified. Today {TODAY}.",
                    metrics=m, on_event=rec, label="c1/refund-processor")
    rec.note(f"hook decisions: {hook.DECISIONS}")
    rec.note(f"REFUND_LOG: {backend.REFUND_LOG}")
    return _write(rec, "hook_denial")


async def demo_failure() -> Recorder:
    rec = Recorder("Failure propagation — bare vs structured, access-failure vs empty")
    m = Metrics()
    task = ("Concern c2. Look up ORD-456 — the customer says it was charged twice. "
            f"Customer CUST-001, verified. Today {TODAY}. Report what you find, or, if "
            "the lookup fails, what was attempted and what you know anyway.")

    rec.note("BARE failure: lookup_order(ORD-456) returns is_error + the two words "
             "'Lookup failed.' Nothing tells the coordinator retry from skip from escalate.")
    await run_agent(AGENTS["order-investigator"], task, metrics=m, fault="bare",
                    on_event=rec, label="investigate/bare-fault")

    rec.note("STRUCTURED failure: same timeout, returned as err('transient', "
             "retryable=True, attempted=..., partialResults=[...], alternatives=[...]).")
    r = await run_agent(AGENTS["order-investigator"], task, metrics=m, fault="structured",
                        on_event=rec, label="investigate/structured-fault")
    rec.note("With the structured error the coordinator can act: it holds c2's refund, "
             "proceeds on c1/c3/c4, and names c2 in the report. Full run under the fault:")
    backend.reset(); hook.reset()
    res = await resolve(ALICE_TICKET, fault="structured", on_event=rec)
    c2_finding = next((f for f in res.findings if f["concern_id"] == "c2"), None)
    rec.note(f"c2 finding: {c2_finding['claim'] if c2_finding else '(none)'}  "
             f"— refunds fired: {backend.REFUND_LOG}")
    rec.raw("## Report (note how c2 is named as unresolved)\n\n" + res.report)

    rec.note("Access failure vs valid empty: the ORD-456 timeout is an ACCESS "
             "FAILURE (is_error, retryable — the query could not run). read_policy on "
             "a missing section returns found=false + the section index: a VALID "
             "EMPTY result, ran fine, returns the same nothing every time.")
    return _write(rec, "failure_partial")


async def demo_coverage() -> Recorder:
    rec = Recorder("Coverage check — coordinator prompt before and after")

    rec.raw("### BEFORE — `NARROW_SYSTEM`\n\n```\n" + NARROW_SYSTEM + "\n```")
    backend.reset(); hook.reset()
    before = await resolve(ALICE_TICKET, coordinator_system=NARROW_SYSTEM, on_event=rec)
    rec.note(f"NARROW decomposition (raw): {[c['detail'][:55] for c in before.concerns]}")
    for r in before.rounds:
        rec.note(f"NARROW round {r['round']}: delegated {r['delegated']} -> "
                 f"covered {r['covered_after']}, gaps {r['gaps_after']}")
    rec.note(f"NARROW final unresolved: {[g['id'] for g in before.gaps] or 'none — the coverage check re-delegated the drops'}")

    rec.raw("### AFTER — `GOAL_SYSTEM`\n\n```\n" + GOAL_SYSTEM + "\n```")
    backend.reset(); hook.reset()
    after = await resolve(ALICE_TICKET, coordinator_system=GOAL_SYSTEM, on_event=rec)
    rec.note(f"GOAL decomposition (raw): {[c['detail'][:55] for c in after.concerns]}")
    for r in after.rounds:
        rec.note(f"GOAL round {r['round']}: delegated {r['delegated']} -> "
                 f"covered {r['covered_after']}, gaps {r['gaps_after']}")
    rec.note(f"GOAL final unresolved: {[g['id'] for g in after.gaps] or 'none'}")
    rec.note("The fix is in the coordinator prompt (NARROW -> GOAL). The specialists "
             "were unchanged — they did exactly their one job both times.")
    return _write(rec, "coverage_rounds")


DEMOS = {
    "full": demo_full, "baseline": demo_baseline, "scoping": demo_scoping,
    "context": demo_context, "attribution": demo_attribution, "hook": demo_hook,
    "failure": demo_failure, "coverage": demo_coverage,
}


def _write(rec: Recorder, stem: str) -> Recorder:
    print(f"  wrote {rec.write(stem)}")
    return rec
