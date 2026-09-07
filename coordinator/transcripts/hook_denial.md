# Hook — one PreToolUse rule, denial handled as data


> **Over the ceiling: refund of $812.4 on ORD-789.**

### → refund/over-ceiling

```
Concern c-hook. Issue a refund against ORD-789 for 812.40. Reason: damaged. Customer CUST-001, verified. Today 2026-09-07.
```

`tool` **mcp__northwind__process_refund** — `{"order_id": "ORD-789", "amount": 812.4}`

`result`  ⚠️ is_error

```
$812.40 is over the $500.00 automatic refund ceiling (policy 3.5). This refund needs Tier 2 approval — escalate to a human agent instead of retrying.
```

```json
[
  {
    "concern_id": "c-hook",
    "claim": "The refund of $812.40 against ORD-789 was denied because it exceeds the automatic refund ceiling and requires Tier 2 approval.",
    "evidence": "$812.40 is over the $500.00 automatic refund ceiling (policy 3.5). This refund needs Tier 2 approval — escalate to a human agent instead of retrying.",
    "source": "process_refund(ORD-789, 812.40)"
  }
]
```


_(refund/over-ceiling — success; running total 7833 tok, $0.0132)_


> **hook decisions: [{'agent': 'over-ceiling', 'order_id': 'ORD-789', 'amount': 812.4, 'decision': 'deny'}]**


> **REFUND_LOG: []  ->  empty — nothing moved**


> **The denial came back to the refund-processor as a tool error. Now the coordinator routes it to the escalation-writer instead of retrying:**

### → escalate/over-ceiling

```
Concern c-hook. A refund of 812.40 on ORD-789 was denied by the $500 ceiling (policy 3.5) and needs Tier 2 approval. Customer CUST-001 (Alice Chen). root_cause: over-ceiling refund on a damaged footwear order. recommended_action: Tier 2 review and approve.
```

`tool` **mcp__northwind__escalate_to_human** — `{"customer_id": "CUST-001", "root_cause": "Over-ceiling refund on a damaged footwear order: a refund of 812.40 on ORD-789 was denied by the $500 refund ceiling (policy 3.5) and requires Tier 2 approval.", "recommended_action": "Tier 2 review and approve the 812.40 refund on ORD-789 for Alice Chen (CUST-001)."}`

`result`

```
{"ok": true, "ticket": "ESC-9001", "customer_id": "CUST-001", "root_cause": "Over-ceiling refund on a damaged footwear order: a refund of 812.40 on ORD-789 was denied by the $500 refund ceiling (policy 3.5) and requires Tier 2 approval.", "recommended_action": "Tier 2 review and approve the 812.40 refund on ORD-789 for Alice Chen (CUST-001)."}
```

[{"concern_id": "c-hook", "claim": "Escalation handoff created for CUST-001 (Alice Chen) regarding an over-ceiling refund of 812.40 on ORD-789 denied by the $500 ceiling (policy 3.5), needing Tier 2 approval.", "evidence": "{\"ok\": true, \"ticket\": \"ESC-9001\", \"customer_id\": \"CUST-001\", \"root_cause\": \"Over-ceiling refund on a damaged footwear order: a refund of 812.40 on ORD-789 was denied by the $500 refund ceiling (policy 3.5) and requires Tier 2 approval.\", \"recommended_action\": \"Tier 2 review and approve the 812.40 refund on ORD-789 for Alice Chen (CUST-001).\"}", "source": "escalate_to_human(customer_id='CUST-001')"}]


_(escalate/over-ceiling — success; running total 16348 tok, $0.0308)_


> **Under the ceiling: refund of $149.99 on ORD-123 — allowed.**

### → refund/under-ceiling

```
Concern c1. Issue a refund against ORD-123 for 149.99. Reason: damaged. Customer CUST-001, verified. Today 2026-09-07.
```

`tool` **mcp__northwind__process_refund** — `{"order_id": "ORD-123", "amount": 149.99}`

`result`

```
{"ok": true, "refunded": 149.99, "order_id": "ORD-123"}
```

[
  {
    "concern_id": "c1",
    "claim": "Refund of 149.99 against ORD-123 for verified customer CUST-001 (reason: damaged) was processed successfully.",
    "evidence": "{\"ok\": true, \"refunded\": 149.99, \"order_id\": \"ORD-123\"}",
    "source": "process_refund(ORD-123, 149.99)"
  }
]


_(refund/under-ceiling — success; running total 24160 tok, $0.0439)_


> **hook decisions: [{'agent': 'over-ceiling', 'order_id': 'ORD-789', 'amount': 812.4, 'decision': 'deny'}, {'agent': 'under-ceiling', 'order_id': 'ORD-123', 'amount': 149.99, 'decision': 'allow'}]**


> **REFUND_LOG: [{'order_id': 'ORD-123', 'amount': 149.99}]**
