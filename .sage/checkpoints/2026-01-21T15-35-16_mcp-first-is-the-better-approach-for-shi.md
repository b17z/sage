---
id: 2026-01-21T15-35-16_mcp-first-is-the-better-approach-for-shi
type: checkpoint
ts: '2026-01-21T15:35:16.384617+00:00'
trigger: synthesis
confidence: 0.8
message_count: 0
token_estimate: 0
action_type: learning
---

# Should ShipCheck (a production-readiness auditor for vibe-coded projects) be built CLI-first or MCP-first?

## Thesis
MCP-first is the better approach for ShipCheck because target users are already in AI-assisted editors (Cursor, Claude Code), the Socratic tutoring flow maps naturally to AI conversation turns, and MCP offloads the interactive REPL work to Claude. CLI should be a thin wrapper added second for CI/CD and terminal users.

## Key Evidence
- PRD's own admission that 'CLI ships faster and naturally evolves into a Claude Code plugin' - that plugin IS MCP
- Target users are vibe coders using Cursor/Copilot who are already conversing with AI
- The fix/verify flow becomes trivial with MCP because Claude handles the Socratic dialogue natively
- MCP tools are simpler than building CLI arg parsing + terminal REPL
- VS Code extension may be unnecessary since Cursor is adding MCP support

## Reasoning Trace
Analyzed the PRD's CLI-first rationale (file system access, no deployment complexity, path to plugin). Recognized that 'Claude Code plugin' mentioned in PRD is essentially MCP. Compared effort/value of CLI REPL vs MCP for Socratic tutoring - MCP wins because Claude already handles conversation. Identified hybrid approach: MCP-first for primary interface, CLI as thin wrapper for automation.

## Open Questions
- Will Cursor's MCP support be robust enough?
- Is there demand for standalone CLI in CI/CD pipelines?
- How to handle state persistence across MCP sessions?
