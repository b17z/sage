# Agentic Design Patterns

Reference patterns for building effective AI agent systems.

## Core Patterns

### Prompt Chaining
Break complex tasks into sequential phases, each building on the previous.
- Explore → Analyze → Synthesize
- Research → Gap Analysis → Follow-up → Summary

### Reflection
Have the agent evaluate its own output for gaps, errors, or improvements.
- "What questions remain unanswered?"
- "What claims need verification?"

### Tool Use
Provide agents with specific, well-defined tools.
- Limit to 1-5 tools (more degrades reliability)
- Clear input/output contracts
- Graceful failure handling

### Routing
Direct queries to appropriate specialists based on content.
- Multi-skill queries for cross-domain analysis
- Skill selection based on query classification

### Memory Management
Maintain context across interactions.
- Session artifacts for long-running research
- Shared memory for cross-skill insights
- History for continuity

### Human-in-the-Loop
Keep humans involved in key decisions.
- Manual summarization (human decides what matters)
- Explicit "remember" commands
- Approval gates for significant actions

## Anti-Patterns to Avoid

### Tool Overload
More than 5 tools significantly degrades agent reliability.

### No Exit Conditions
Always define maximum iterations, token limits, or time bounds.

### Premature Multi-Agent
Start with single agents; add complexity only when needed.

### Black Box Agents
Log everything; make agent behavior inspectable.
