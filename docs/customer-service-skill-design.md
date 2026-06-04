# Customer Service Skill Design

## Goal

`customer_service_core` is the first portable skill package for turning a general agent into an intelligent customer-service agent.

It is intentionally not a backend-only implementation. The same package should be understandable by:

- This repository's agent runtime loop.
- Claude Code or Codex-style engineering agents that can read `SKILL.md`.
- Future skill loaders that read `manifest.yaml` and references.

## Boundary

The standard agent framework owns:

- action loop
- context
- observations
- LLM interface
- MCP gateway interface
- session state
- skill registry

`customer_service_core` owns:

- customer-service identity
- user-facing tone
- conversation policy
- clarification strategy
- when to request MCP
- how to explain MCP results
- when to request handoff

MCP owns:

- real user lookup
- real order lookup
- real knowledge search
- real ticket actions
- real handoff request
- final permission checks

## Current Package

```text
skills/customer_service_core/
  manifest.yaml
  SKILL.md
  agents/
    openai.yaml
  references/
    persona.md
    conversation_policy.md
    mcp_policy.md
    handoff_policy.md
    identity_policy.md
    evaluation_cases.md
```

## Runtime Mapping

When integrated into the backend runtime, this skill should map to the existing loop actions:

- Need natural answer: `LLMAction`
- Need real data: `MCPToolAction`
- Need more user info: `AskUserAction`
- Need escalation: `HandoffAction`
- Response ready: `FinalAnswerAction`

The framework should not hard-code customer-service concepts. It should load this skill, pass `TurnContext`, available MCP tools, and conversation state, then let the skill decide the next action.

## Next Implementation Step

The next step is a file-based skill loader:

1. Read `skills/*/manifest.yaml`.
2. Register discovered skills in `SkillRegistry`.
3. Add a generic markdown-backed skill adapter for `customer_service_core`.
4. Inject `SKILL.md` plus selected references into the LLM system prompt.
5. Keep MCP optional until tool actions are needed.
