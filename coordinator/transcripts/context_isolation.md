# Context isolation — a specialist starts empty


> **WRONG: the policy-analyst is asked only 'Is ORD-789 still inside its return window?' It has read_policy but no order access and no clock — it cannot get the delivery date or today's date.**

### → policy/no-facts

```
Is order ORD-789 still inside its return window?
```

`tool` **mcp__northwind__read_policy** — `{"section": "2.1"}`

`result`

```
{"section": "2.1", "text": "Standard return window: 30 calendar days from delivery date.", "found": true}
```

`tool` **mcp__northwind__read_policy** — `{"section": "2.2"}`

`result`

```
{"section": "2.2", "text": "Footwear and apparel may be returned within 45 days if unworn with tags attached.", "found": true}
```

```json
[
  {
    "concern_id": "none",
    "claim": "I cannot determine whether ORD-789 is inside its return window because my prompt contains no delivered_on date, sku, or customer details for ORD-789, and I cannot look order data up.",
    "evidence": "Standard return window: 30 calendar days from delivery date. (policy 2.1); Footwear and apparel may be returned within 45 days if unworn with tags attached. (policy 2.2) — but no delivery date for ORD-789 was provided to apply either rule.",
    "source": "missing order facts in prompt (no lookup tool available); policy 2.1 and policy 2.2"
  }
]
```


_(policy/no-facts — success; running total 14823 tok, $0.0401)_


> **RIGHT: every fact is in the prompt.**

### → policy/with-facts

```
Concern c3. Is ORD-789 still returnable? Facts: item is footwear (SKU FW-2201), delivered 2026-07-29, today 2026-09-07, condition unworn, amount 812.4. Cite the clause.
```

`tool` **mcp__northwind__read_policy** — `{"section": "1"}`

`result`

```
{"section": "1", "text": null, "found": false, "available_sections": ["2.1", "2.2", "2.3", "3.4", "3.5", "5.2"]}
```

`tool` **mcp__northwind__read_policy** — `{"section": "2"}`

`result`

```
{"section": "2", "text": null, "found": false, "available_sections": ["2.1", "2.2", "2.3", "3.4", "3.5", "5.2"]}
```

`tool` **mcp__northwind__read_policy** — `{"section": "2.1"}`

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

`tool` **mcp__northwind__read_policy** — `{"section": "5.2"}`

`result`

```
{"section": "3.5", "text": "Refund requests over $500 require Tier 2 approval.", "found": true}
```

`result`

```
{"section": "5.2", "text": "Duplicate charges: once a second charge for one order is confirmed, refund the extra charge to the original payment method. No further approval is needed below the section 3.5 ceiling.", "found": true}
```

```json
[
  {
    "concern_id": "c3",
    "claim": "ORD-789 is within the return window: footwear returned unworn may be returned within 45 days of delivery, and only 40 days have elapsed (delivered 2026-07-29, today 2026-09-07).",
    "evidence": "Footwear and apparel may be returned within 45 days if unworn with tags attached.",
    "source": "policy 2.2"
  },
  {
    "concern_id": "c3",
    "claim": "The return qualifies under the footwear rule rather than the 30-day standard window, which would otherwise have expired at 40 days.",
    "evidence": "Standard return window: 30 calendar days from delivery date.",
    "source": "policy 2.1"
  },
  {
    "concern_id": "c3",
    "claim": "Condition is given as unworn, but 'tags attached' is not stated in the facts, so approval is conditional on tags being present.",
    "evidence": "condition unworn; policy 2.2 requires 'unworn with tags at
… (+279 chars)


_(policy/with-facts — success; running total 38344 tok, $0.0698)_
