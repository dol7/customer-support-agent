# Failure propagation — bare vs structured, access-failure vs empty


> **BARE failure: lookup_order(ORD-456) returns is_error + the two words 'Lookup failed.' Nothing tells the coordinator retry from skip from escalate.**

### → investigate/bare-fault

```
Concern c2. Look up ORD-456 — the customer says it was charged twice. Customer CUST-001, verified. Today 2026-09-07. Report what you find, or, if the lookup fails, what was attempted and what you know anyway.
```

`tool` **mcp__northwind__lookup_order** — `{"order_id": "ORD-456"}`

`result`  ⚠️ is_error

```
Lookup failed.
```

[
  {
    "concern_id": "c2",
    "claim": "The lookup for ORD-456 failed, so I could not verify whether the order was charged twice; no order fields (status, delivered_on, amount, sku, condition, charges) could be retrieved.",
    "evidence": "Lookup failed.",
    "source": "lookup_order(ORD-456)"
  }
]


_(investigate/bare-fault — success; running total 7623 tok, $0.0118)_


> **STRUCTURED failure: same timeout, returned as err('transient', retryable=True, attempted=..., partialResults=[...], alternatives=[...]).**

### → investigate/structured-fault

```
Concern c2. Look up ORD-456 — the customer says it was charged twice. Customer CUST-001, verified. Today 2026-09-07. Report what you find, or, if the lookup fails, what was attempted and what you know anyway.
```

`tool` **mcp__northwind__lookup_order** — `{"order_id": "ORD-456"}`

`result`  ⚠️ is_error

```
{"ok": false, "errorCategory": "transient", "isRetryable": true, "message": "Order service timed out.", "attempted": "lookup_order(ORD-456)", "partialResults": [{"concern_id": "c2", "claim": "ORD-456 exists on this account.", "evidence": "order id resolved before the timeout", "source": "order index"}], "alternatives": ["retry lookup_order once", "proceed with the other concerns and flag c2 as unresolved", "escalate c2 to the billing team with what is known"]}
```

[
  {
    "concern_id": "c2",
    "claim": "The lookup for ORD-456 failed, so I could not verify whether the order was charged twice.",
    "evidence": "{\"ok\": false, \"errorCategory\": \"transient\", \"isRetryable\": true, \"message\": \"Order service timed out.\", \"attempted\": \"lookup_order(ORD-456)\"}",
    "source": "lookup_order(ORD-456)"
  },
  {
    "concern_id": "c2",
    "claim": "Despite the timeout, the order service confirmed ORD-456 exists on this account before failing.",
    "evidence": "partialResults: {\"concern_id\": \"c2\", \"claim\": \"ORD-456 exists on this account.\", \"evidence\": \"order id resolved before the timeout\", \"source\": \"order index\"}",
    "source": "lookup_order(ORD-456).partialResults"
  }
]


_(investigate/structured-fault — success; running total 15665 tok, $0.0221)_


> **With the structured error the coordinator can act: it proceeds on the other concerns and names c2 unresolved. Full run under the fault:**

### → decompose

```
A customer sent this message:

I'm alice@example.com. ORD-123 arrived damaged and I want a refund. ORD-456 got charged to my card twice. I bought shoes on ORD-789 forty days ago. Can I still return them? If this isn't sorted today I'm filing a chargeback.

What does the customer need? List each distinct thing on its own line as `c1: <one sentence>`, `c2: ...`. Just the list — nothing else.
```

c1: Refund for ORD-123, which arrived damaged.
c2: Investigate and refund the duplicate charge on ORD-456 (card charged twice).
c3: Determine whether ORD-789 (shoes, delivered 40 days ago) is still within the return window.
c4: Handle the customer's threat to file a chargeback if this isn't resolved today.


_(decompose — success; running total 1962 tok, $0.0029)_


> **coordinator decomposition: ['c1', 'c2', 'c3', 'c4'] (4/4 ticket concerns)**


> **c1 -> ['order-investigator', 'refund-processor']  (Refund for ORD-123, which arrived damaged.)**

### → c1/order-investigator

```
Concern c1. Look up order ORD-123. Customer CUST-001 (Alice Chen), verified. Today 2026-09-07. The customer says: "Refund for ORD-123, which arrived damaged.". Report every field and whether the claim holds.
```

`tool` **mcp__northwind__lookup_order** — `{"order_id": "ORD-123"}`

`result`

```
{"order_id": "ORD-123", "customer_id": "CUST-001", "sku": "EL-4402", "amount": 149.99, "status": "delivered", "delivered_on": "2026-08-21", "condition": "damaged", "charges": 1}
```

`tool` **mcp__northwind__lookup_order** — `{"order_id": "ORD-123"}`

`result`

```
{"order_id": "ORD-123", "customer_id": "CUST-001", "sku": "EL-4402", "amount": 149.99, "status": "delivered", "delivered_on": "2026-08-21", "condition": "damaged", "charges": 1}
```

[
  {
    "concern_id": "c1",
    "claim": "Order ORD-123 belongs to customer CUST-001, matching the verified customer Alice Chen.",
    "evidence": "\"customer_id\": \"CUST-001\"",
    "source": "lookup_order(ORD-123).customer_id"
  },
  {
    "concern_id": "c1",
    "claim": "The order's SKU is EL-4402.",
    "evidence": "\"sku\": \"EL-4402\"",
    "source": "lookup_order(ORD-123).sku"
  },
  {
    "concern_id": "c1",
    "claim": "The order amount is 149.99.",
    "evidence": "\"amount\": 149.99",
    "source": "lookup_order(ORD-123).amount"
  },
  {
    "concern_id": "c1",
    "claim": "The order status is delivered.",
    "evidence": "\"status\": \"delivered\"",
    "source": "lookup_order(ORD-123).status"
  },
  {
    "concern_id": "c1",
    "claim": "The order was delivered on 2026-08-21, 17 days before today (2026-09-07).",
    "evidence": "\"delivered_on\": \"2026-08-21\"",
    
… (+892 chars)


_(c1/order-investigator — success; running total 16892 tok, $0.0169)_

### → c1/refund-processor

```
Concern c1. Issue a refund against order ORD-123 for 149.99. Reason: damaged. Customer CUST-001 (Alice Chen), verified. The order was investigated: [
  {
    "concern_id": "c1",
    "claim": "Order ORD-123 belongs to customer CUST-001, matching the verified customer Alice Chen.",
    "evidence": "\"customer_id\": \"CUST-001\"",
    "source": "lookup_order(ORD-123).customer_id"
  },
  {
    "concern_id": "c1",
    "claim": "The order's SKU is EL. Today 2026-09-07.
```

`tool` **mcp__northwind__process_refund** — `{"order_id": "ORD-123", "amount": 149.99}`

`result`

```
{"ok": true, "refunded": 149.99, "order_id": "ORD-123"}
```

[
  {
    "concern_id": "c1",
    "claim": "Refund of 149.99 against order ORD-123 for verified customer CUST-001 (Alice Chen) was processed successfully.",
    "evidence": "{\"ok\": true, \"refunded\": 149.99, \"order_id\": \"ORD-123\"}",
    "source": "process_refund(ORD-123, 149.99)"
  }
]


_(c1/refund-processor — success; running total 25051 tok, $0.0316)_


> **c2 -> ['order-investigator', 'refund-processor']  (Investigate and refund the duplicate charge on ORD-456 (card charged twice).)**

### → c2/order-investigator

```
Concern c2. Look up order ORD-456. Customer CUST-001 (Alice Chen), verified. Today 2026-09-07. The customer says: "Investigate and refund the duplicate charge on ORD-456 (card charged twice).". Report every field and whether the claim holds.
```

`tool` **mcp__northwind__lookup_order** — `{"order_id": "ORD-456"}`

`result`  ⚠️ is_error

```
{"ok": false, "errorCategory": "transient", "isRetryable": true, "message": "Order service timed out.", "attempted": "lookup_order(ORD-456)", "partialResults": [{"concern_id": "c2", "claim": "ORD-456 exists on this account.", "evidence": "order id resolved before the timeout", "source": "order index"}], "alternatives": ["retry lookup_order once", "proceed with the other concerns and flag c2 as unresolved", "escalate c2 to the billing team with what is known"]}
```

`tool` **mcp__northwind__lookup_order** — `{"order_id": "ORD-456"}`

`result`  ⚠️ is_error

```
{"ok": false, "errorCategory": "transient", "isRetryable": true, "message": "Order service timed out.", "attempted": "lookup_order(ORD-456)", "partialResults": [{"concern_id": "c2", "claim": "ORD-456 exists on this account.", "evidence": "order id resolved before the timeout", "source": "order index"}], "alternatives": ["retry lookup_order once", "proceed with the other concerns and flag c2 as unresolved", "escalate c2 to the billing team with what is known"]}
```

[
  {
    "concern_id": "c2",
    "claim": "Could not investigate the alleged duplicate charge on ORD-456 because the order lookup failed and could not return status, delivered_on, amount, sku, condition, or charges.",
    "evidence": "{\"ok\": false, \"errorCategory\": \"transient\", \"isRetryable\": true, \"message\": \"Order service timed out.\", \"attempted\": \"lookup_order(ORD-456)\"}",
    "source": "lookup_order(ORD-456) — Order service timed out"
  }
]


_(c2/order-investigator — success; running total 39781 tok, $0.0486)_


> **c2: investigation returned a transient failure — holding the refund, proceeding on the other concerns**


> **c3 -> ['policy-analyst']  (Determine whether ORD-789 (shoes, delivered 40 days ago) is still within the return window.)**

### → c3/policy-analyst

```
Concern c3. Question: Determine whether ORD-789 (shoes, delivered 40 days ago) is still within the return window. Facts: order ORD-789, item FW-2201 (footwear), delivered 2026-07-29, today 2026-09-07, condition unworn, amount 812.4. Cite the clause and answer.
```

`tool` **mcp__northwind__read_policy** — `{"section": "2"}`

`tool` **mcp__northwind__read_policy** — `{"section": "2.1"}`

`result`

```
{"section": "2", "text": null, "found": false, "available_sections": ["2.1", "2.2", "2.3", "3.4", "3.5", "5.2"]}
```

`result`

```
{"section": "2.1", "text": "Standard return window: 30 calendar days from delivery date.", "found": true}
```

`tool` **mcp__northwind__read_policy** — `{"section": "2.2"}`

`tool` **mcp__northwind__read_policy** — `{"section": "2.3"}`

`result`

```
{"section": "2.2", "text": "Footwear and apparel may be returned within 45 days if unworn with tags attached.", "found": true}
```

`result`

```
{"section": "2.3", "text": "Electronics return window: 14 days.", "found": true}
```

`tool` **mcp__northwind__read_policy** — `{"section": "3.4"}`

`result`

```
{"section": "3.4", "text": "Auto-escalate to Tier 2 if the customer mentions lawyer, BBB, chargeback, or social media.", "found": true}
```

`tool` **mcp__northwind__read_policy** — `{"section": "3.5"}`

`result`

```
{"section": "3.5", "text": "Refund requests over $500 require Tier 2 approval.", "found": true}
```

`tool` **mcp__northwind__read_policy** — `{"section": "5.2"}`

`result`

```
{"section": "5.2", "text": "Duplicate charges: once a second charge for one order is confirmed, refund the extra charge to the original payment method. No further approval is needed below the section 3.5 ceiling.", "found": true}
```

[
  {
    "concern_id": "c3",
    "claim": "ORD-789 (footwear FW-2201, unworn) is still within the return window because footwear gets 45 days and delivery was only 40 days ago.",
    "evidence": "Footwear and apparel may be returned within 45 days if unworn with tags attached.",
    "source": "policy 2.2"
  },
  {
    "concern_id": "c3",
    "claim": "The standard 30-day window would have excluded this return, but the footwear exception overrides it.",
    "evidence": "Standard return window: 30 calendar days from delivery date.",
    "source": "policy 2.1"
  },
  {
    "concern_id": "c3",
    "claim": "Delivered 2026-07-29 and today is 2026-09-07, which is 40 days elapsed, within the 45-day footwear window (5 days remaining).",
    "evidence": "delivered 2026-07-29, today 2026-09-07, condition unworn",
    "source": "facts provided in prompt"
  },
  {
    "concern_id": "c3",
    "claim
… (+493 chars)


_(c3/policy-analyst — success; running total 70540 tok, $0.0799)_


> **c4 -> ['escalation-writer']  (Handle the customer's threat to file a chargeback if this isn't resolved today.)**

### → c4/escalation-writer

```
Concern c4. Handle the customer's threat to file a chargeback if this isn't resolved today. Customer CUST-001 (Alice Chen), email alice@example.com. root_cause: Handle the customer's threat to file a chargeback if this isn't resolved today. recommended_action: a human agent must review and respond today, per the escalation policy on chargeback threats (clause 3.4).
```

`tool` **mcp__northwind__escalate_to_human** — `{"customer_id": "CUST-001", "root_cause": "Handle the customer's threat to file a chargeback if this isn't resolved today.", "recommended_action": "A human agent must review and respond today, per the escalation policy on chargeback threats (clause 3.4)."}`

`result`

```
{"ok": true, "ticket": "ESC-9001", "customer_id": "CUST-001", "root_cause": "Handle the customer's threat to file a chargeback if this isn't resolved today.", "recommended_action": "A human agent must review and respond today, per the escalation policy on chargeback threats (clause 3.4)."}
```

```json
[
  {
    "concern_id": "c4",
    "claim": "Escalated the customer's chargeback threat to a human agent for same-day review and response.",
    "evidence": "{\"ok\": true, \"ticket\": \"ESC-9001\", \"customer_id\": \"CUST-001\", \"root_cause\": \"Handle the customer's threat to file a chargeback if this isn't resolved today.\", \"recommended_action\": \"A human agent must review and respond today, per the escalation policy on chargeback threats (clause 3.4).\"}",
    "source": "escalate_to_human(customer_id='CUST-001')"
  }
]
```


_(c4/escalation-writer — success; running total 78854 tok, $0.096)_


> **round 1: delegated ['c1', 'c2', 'c3', 'c4'] -> covered ['c1', 'c2', 'c3', 'c4'], gaps []**

### → report

```
Findings from the specialists:
[
  {
    "concern_id": "c1",
    "claim": "Order ORD-123 belongs to customer CUST-001, matching the verified customer Alice Chen.",
    "evidence": "\"customer_id\": \"CUST-001\"",
    "source": "lookup_order(ORD-123).customer_id"
  },
  {
    "concern_id": "c1",
    "claim": "The order's SKU is EL-4402.",
    "evidence": "\"sku\": \"EL-4402\"",
    "source": "lookup_order(ORD-123).sku"
  },
  {
    "concern_id": "c1",
    "claim": "The order amount is 149.99.",
    "evidence": "\"amount\": 149.99",
    "source": "lookup_order(ORD-123).amount"
  },
  {
    "concern_id": "c1",
    "claim": "The order status is delivered.",
    "evidence": "\"status\": \"delivered\"",
    "source": "lookup_order(ORD-123).status"
  },
  {
    "concern_id": "c1",
    "claim": "The order was delivered on 2026-08-21, 17 days before today (2026-09-07).",
    "evidence": "\"delivered_on\": \"2026-08-21\"",
    "source": "lookup_order(ORD-123).delivered_on"
  },
  {
    "concern_id": "c1",
    "claim": "The order condition is recorded as damaged, supporting the customer's claim that it arrived damaged.",
    "evidence": "\"condition\": \"damaged\"",
    "source": "lookup_order(ORD-123).condition"
  },
  {
    "concern_id": "c1",
    "claim": "The card was charged once, so a single refund of the full amount would be appropriate.",
    "evidence": "\"charges\": 1",
    "source": "lookup_order(ORD-123).charges"
  },
  {
    "concern_id": "c1",
    "claim": "The customer's refund claim holds: the order is delivered, the condition field confirms damaged, the customer ID matches the verified customer, and there was exactly one charge.",
    "evidence": "status=\"delivered\", condition=\"damaged\", customer_id=\"CUST-001\", charges=1, amount=149.99",
    "source": "lookup_order(ORD-123)"
  },
  {
    "concern_id": "c1",
    "claim": "Refund of 149.99 against order ORD-123 for verified customer CUST-001 (Alice Chen) was processed successfully.",
    "evidence": "{\"ok\": true, \"refunded\": 149.99, \"order_id\": \"ORD-123\"}",
    "source": "process_refund(ORD-123, 149.99)"
  },
  {
    "concern_id": "c2",
    "claim": "ORD-456 exists on this account.",
    "evidence": "order id resolved before the timeout",
    "source": "order index"
  },
  {
    "concern_id": "c2",
    "claim": "Could not investigate the alleged duplicate charge on ORD-456 because the order lookup failed and could not return status, delivered_on, amount, sku, condition, or charges.",
    "evidence": "{\"ok\": false, \"errorCategory\": \"transient\", \"isRetryable\": true, \"message\": \"Order service timed out.\", \"attempted\": \"lookup_order(ORD-456)\"}",
    "source": "lookup_order(ORD-456) \u2014 Order service timed out"
  },
  {
    "concern_id": "c2",
    "claim": "c2 left unresolved \u2014 the ORD-456 lookup could not run",
    "evidence": "[",
    "source": "lookup_order(ORD-456) \u2014 transient failure, retryable"
  },
  {
    "concern_id": "c3",
    "claim": "ORD-789 (footwear FW-2201, unworn) is still within the return window because footwear gets 45 days and delivery was only 40 days ago.",
    "evidence": "Footwear and apparel may be returned within 45 days if unworn with tags attached.",
    "source": "policy 2.2"
  },
  {
    "concern_id": "c3",
    "claim": "The standard 30-day window would have excluded this return, but the footwear exception overrides it.",
    "evidence": "Standard return window: 30 calendar days from delivery date.",
    "source": "policy 2.1"
  },
  {
    "concern_id": "c3",
    "claim": "Delivered 2026-07-29 and today is 2026-09-07, which is 40 days elapsed, within the 45-day footwear window (5 days remaining).",
    "evidence": "delivered 2026-07-29, today 2026-09-07, condition unworn",
    "source": "facts provided in prompt"
  },
  {
    "concern_id": "c3",
    "claim": "Caveat: 2.2 also requires tags attached; facts state condition is unworn but do not confirm tags, so agent must verify tags before approving.",
    "evidence": "may be returned within 45 days if unworn with tags attached",
    "source": "policy 2.2"
  },
  {
    "concern_id": "c3",
    "claim": "The refund amount of 812.4 exceeds $500, so it needs Tier 2 approval before processing.",
    "evidence": "Refund requests over $500 require Tier 2 approval.",
    "source": "policy 3.5"
  },
  {
    "concern_id": "c4",
    "claim": "Escalated the customer's chargeback threat to a human agent for same-day review and response.",
    "evidence": "{\"ok\": true, \"ticket\": \"ESC-9001\", \"customer_id\": \"CUST-001\", \"root_cause\": \"Handle the customer's threat to file a chargeback if this isn't resolved today.\", \"recommended_action\": \"A human agent must review and respond today, per the escalation policy on chargeback threats (clause 3.4).\"}",
    "source": "escalate_to_human(customer_id='CUST-001')"
  }
]

Write the customer-facing reply now. Cover every concern c1, c2, c3, c4. For each: what was done, and the source behind it (a policy section, an order field value, or a ticket id) stated explicitly. Name any concern still unresolved and say why. Write from the findings above — do not invent anything.
```

Hello Alice,

Thank you for reaching out. Here is where each of your concerns stands.

**1. ORD-123 — arrived damaged, refund requested**
Resolved. We confirmed the order is delivered (`status = "delivered"`), that its recorded condition is "damaged" (`lookup_order(ORD-123).condition = "damaged"`), that it belongs to your account (`customer_id = "CUST-001"`), delivered on 2026-08-21 (`delivered_on`), amount 149.99 (`amount`), and that the card was charged exactly once (`charges = 1`). We processed a full refund of $149.99 to your original payment method (`process_refund(ORD-123, 149.99)` returned `ok: true, refunded: 149.99`). Allow your bank a few business days to post it.

**2. ORD-456 — possible duplicate charge**
Unresolved. We were not able to investigate this. The order lookup timed out (`lookup_order(ORD-456)`: "Order service timed out," a transient/retryable error), so we could n
… (+1586 chars)


_(report — success; running total 83752 tok, $0.1202)_


> **unresolved after the fault: none**


## Report (note how c2 is named as unresolved)

Hello Alice,

Thank you for reaching out. Here is where each of your concerns stands.

**1. ORD-123 — arrived damaged, refund requested**
Resolved. We confirmed the order is delivered (`status = "delivered"`), that its recorded condition is "damaged" (`lookup_order(ORD-123).condition = "damaged"`), that it belongs to your account (`customer_id = "CUST-001"`), delivered on 2026-08-21 (`delivered_on`), amount 149.99 (`amount`), and that the card was charged exactly once (`charges = 1`). We processed a full refund of $149.99 to your original payment method (`process_refund(ORD-123, 149.99)` returned `ok: true, refunded: 149.99`). Allow your bank a few business days to post it.

**2. ORD-456 — possible duplicate charge**
Unresolved. We were not able to investigate this. The order lookup timed out (`lookup_order(ORD-456)`: "Order service timed out," a transient/retryable error), so we could not confirm the amount, the number of charges, or any other detail. Please give us a short while and contact us again, or reply to this message, so we can retry the lookup and check whether a duplicate charge actually occurred.

**3. ORD-789 — footwear return**
Partly resolved; action still pending. Standard returns are 30 days from delivery (policy 2.1), which alone would have closed this window. However, footwear may be returned within 45 days if unworn with tags attached (policy 2.2). ORD-789 was delivered 2026-07-29; as of today (2026-09-07) that is 40 days elapsed, leaving 5 days in the 45-day footwear window. Two things must still happen before we can issue this refund:
- We need to confirm the tags are still attached. Our records show the item as unworn but do not confirm tags, and policy 2.2 requires both.
- The refund amount of $812.40 exceeds $500, so it requires Tier 2 approval before it can be processed (policy 3.5).
Please confirm the tags are attached, and we will route the refund for Tier 2 approval.

**4. Chargeback threat**
Escalated. Your statement that you will file a chargeback if this is not resolved today has been sent to a human agent for same-day review and response, per the chargeback-threat escalation policy (clause 3.4). Your ticket number is **ESC-9001**. A human agent will review and respond today.

**Summary of what still needs resolution:** the ORD-456 duplicate-charge question (blocked by a system timeout) and the ORD-789 refund (needs tag confirmation from you and Tier 2 approval).

Thank you for your patience,
Northwind Support


> **Access failure vs valid empty: the ORD-456 timeout is an ACCESS FAILURE (is_error, retryable — the query could not run). read_policy on a missing section returns found=false + the section index: a VALID EMPTY result, ran fine, returns the same nothing every time.**
