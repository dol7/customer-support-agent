# Escalation — Bob Carter explicitly asks for a human (ORD-456)

## Customer

> This is Bob Carter, bob.carter@example.com. I've gone back and forth on ORD-456 too many times already. I don't want to go through it again with a bot — please put me through to a real person.

## Assistant turn — stop_reason: `tool_use`

<details><summary>thinking (summarized)</summary>

The customer wants a human right away, so I should escalate promptly without delay. I'll quickly verify their identity first with get_customer to get a proper customer_id, since that improves the ticket quality without much extra delay, then proceed to escalate_to_human.

</details>

I'll get you to a person right away — just pulling up your account so the ticket is complete.

**tool_use** `get_customer`  (id `toolu_01Lk4qk4sX1uhyH3fVeuaieW`)

```json
{
  "full_name": "Bob Carter",
  "email": "bob.carter@example.com",
  "phone": null
}
```

### tool_result — `get_customer`

```json
{
  "ok": true,
  "customer_id": "CUST-1002",
  "name": "Bob Carter",
  "email": "bob.carter@example.com",
  "verified": true,
  "account_status": "active",
  "open_order_count": 0
}
```

## Assistant turn — stop_reason: `tool_use`

**tool_use** `escalate_to_human`  (id `toolu_01KJkWceSzQ4unQgWqxAvxvq`)

```json
{
  "customer_ref": "CUST-1002",
  "order_id": "ORD-456",
  "reason": "Customer Bob Carter (bob.carter@example.com, CUST-1002) explicitly asked to speak with a human agent about ORD-456 and declined to work through it with the automated agent. He states he has already gone back and forth on this order multiple times, so there is prior contact history to review. He did not restate the specific issue with the order to me, so please review the order and prior contact history before calling him back. No refund or other action has been taken by me.",
  "category": "customer_requested_human"
}
```

### tool_result — `escalate_to_human`

```json
{
  "ok": true,
  "ticket_id": "TKT-B98DF14F",
  "status": "open",
  "ticket": {
    "ticket_id": "TKT-B98DF14F",
    "created_at": "2026-09-03T20:26:07Z",
    "status": "open",
    "category": "customer_requested_human",
    "customer": {
      "customer_id": "CUST-1002",
      "name": "Bob Carter",
      "email": "bob.carter@example.com",
      "phone": "+14155550102",
      "account_status": "active"
    },
    "order": {
      "order_id": "ORD-456",
      "status": "delivered",
      "currency": "USD",
      "order_total": "742.00",
      "refundable_amount": "742.00",
      "already_refunded": "0.00"
    },
    "reason": "Customer Bob Carter (bob.carter@example.com, CUST-1002) explicitly asked to speak with a human agent about ORD-456 and declined to work through it with the automated agent. He states he has already gone back and forth on this order multiple times, so there is prior contact history to review. He did not restate the specific issue with the order to me, so please review the order and prior contact history before calling him back. No refund or other action has been taken by me."
  }
}
```

## Assistant turn — stop_reason: `end_turn`

Done, Bob — you're being handed to a human agent. No need to explain anything again to me.

- **Ticket:** TKT-B98DF14F (status: open)
- **Order attached:** ORD-456
- **On file for contact:** bob.carter@example.com and +14155550102

The ticket includes a snapshot of your account and ORD-456, plus a note that you've already been back and forth on this several times, so the agent will review your prior contact history before reaching out rather than starting from scratch. I haven't made any changes to the order.
