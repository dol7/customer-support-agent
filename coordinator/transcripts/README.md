# Transcripts

Generated live against the Claude Agent SDK (`--demo <name>`, model `claude-sonnet-4-6`).

```bash
python -m coordinator --demo all      # regenerate every transcript
python -m coordinator --demo full     # just one
```

| file | demo | shows |
|---|---|---|
| `full_ticket` | `full` | all four concerns handled or escalated; one report; sources intact |
| `baseline_single_agent` | `baseline` | one agent, five tools — the token baseline for reflection Q2 |
| `scoping` | `scoping` | omitted `tools` → full server; explicit `tools` → one tool, refund impossible |
| `context_isolation` | `context` | policy-analyst with no facts says it cannot answer; with facts, cites clause 2.2 |
| `attribution` | `attribution` | raw `{claim,evidence,source}` findings, then the report still naming each source |
| `hook_denial` | `hook` | $812.40 refund denied by the one PreToolUse hook; `REFUND_LOG` empty; escalation instead |
| `failure_partial` | `failure` | bare vs structured failure; the coordinator names c2 unresolved; access-failure vs valid-empty |
| `coverage_rounds` | `coverage` | NARROW coordinator drops the chargeback threat; the coverage check re-delegates it; GOAL covers all four |

Required deliverables map to `full_ticket`, `hook_denial`, `failure_partial`, and
`coverage_rounds`; the rest are supporting evidence.
