---
id: 2026-01-21T17-08-24_sage-v2-2-ships-unified-debug-command-kn
type: checkpoint
ts: '2026-01-21T17:08:24.620522+00:00'
trigger: context_threshold
confidence: 0.9
message_count: 50
token_estimate: 140000
action_type: learning
---

# What knowledge management features should Sage v2.2 include?

## Thesis
Sage v2.2 ships unified debug command, knowledge edit/deprecate/archive with tests. Future automation includes staleness reports, MCP deprecation tools, and recall feedback - prioritized by practical value over ambitious detection.

## Key Evidence
- 642 tests passing after adding 26 new tests
- sage debug shows knowledge + checkpoint matches with score breakdowns
- sage knowledge edit/deprecate/archive commands implemented
- Archived items filtered from recall_knowledge()
- Roadmap updated with Knowledge Maintenance Automation section

## Reasoning Trace
Started with debug command for unified retrieval visibility. Extended to knowledge edit (update in place), deprecate (flag outdated), archive (hide from recall). User asked about automatic triggers - identified staleness, duplicate detection, MCP tools as practical; contradiction detection as ambitious. Updated roadmap to capture these ideas with priorities.

## Open Questions
- Should staleness report be next priority?
- How to track recall events for staleness?
- Token savings tracking - estimate vs measure full transcript?
