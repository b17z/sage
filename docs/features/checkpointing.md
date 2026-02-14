# Checkpointing

Checkpoints capture research state at meaningful moments — not just what you concluded, but *how you got there*.

## Why This Matters

### For Agents
After context compaction, agents lose their working memory. Checkpoints restore research context so agents can continue where they left off.

### For Learning Engineers
The danger with AI-assisted work is **invisible progress**. You got something working, but:
- What code did you actually read?
- What didn't you understand along the way?
- How did you reason through the problem?

Checkpoints are **learning journals** that make the process visible.

## What a Checkpoint Captures

```yaml
---
id: 2026-02-13T12-00-00_jwt-auth-research
type: checkpoint
trigger: synthesis
confidence: 0.85
---

# How does JWT authentication work in this codebase?

## Thesis
JWT tokens with refresh rotation provide stateless auth. Tokens are
validated per-request in middleware, not stored server-side.

## Key Evidence
- JWTHandler.create_token() uses RS256 signing
- Middleware validates on every request
- Refresh tokens stored in httpOnly cookies

## Reasoning Trace
Started by searching for "authentication". Found jwt.py and middleware.py.
Initially confused by why tokens aren't stored - realized they're stateless
by design. The refresh flow was tricky: cookie → new access token → continue.

## Open Questions
- How are tokens revoked if they're stateless?
- What happens on signature key rotation?

## Files Explored
- src/auth/jwt.py
- src/auth/middleware.py
- tests/test_auth.py

## Files Changed
- src/auth/jwt.py (added logging to debug)

## Code References
- src/auth/jwt.py:45-67 (supports) - Token creation logic
- src/auth/middleware.py:23-45 (supports) - Validation flow
```

### The Learning Value

When you review this checkpoint later:

1. **What did you conclude?** — The thesis
2. **What's the evidence?** — Key evidence, code refs
3. **How did you figure it out?** — Reasoning trace
4. **What don't you know yet?** — Open questions
5. **What did you explore?** — Files explored/changed

This is the difference between "I know JWT" and "I understand *how* I learned JWT."

## Checkpoint Fields

| Field | Purpose | Learning Value |
|-------|---------|----------------|
| `core_question` | What you were trying to understand | Your learning goal |
| `thesis` | Your conclusion | What you learned |
| `confidence` | How sure you are (0-1) | Self-assessment |
| `key_evidence` | Facts supporting the thesis | Concrete proof |
| `reasoning_trace` | How you reached the conclusion | Your thinking process |
| `open_questions` | What you still don't know | Next learning steps |
| `sources` | External references (docs, articles) | Where you learned from |
| `tensions` | Conflicting information | Nuance in understanding |
| `files_explored` | Code you read | Your exploration path |
| `files_changed` | Code you modified | Experiments you ran |
| `code_refs` | Specific code evidence | Traceable proof |

**Source:** [`sage/checkpoint.py:69-152`](../../sage/checkpoint.py)

## Triggers

Checkpoints can be saved automatically at meaningful moments:

| Trigger | When | Default Confidence |
|---------|------|-------------------|
| `synthesis` | Combining sources into a conclusion | 0.5 |
| `web_search_complete` | Research with findings | 0.3 |
| `topic_shift` | Conversation changes direction | 0.4 |
| `branch_point` | Decision point ("we could X or Y") | 0.4 |
| `constraint_discovered` | Critical limitation found | 0.4 |
| `context_threshold` | Context usage exceeds 70% | 0.0 |
| `precompact` | Before `/compact` command | 0.0 |
| `manual` | User says "checkpoint" | 0.0 |

**Source:** [`sage/triggers.py`](../../sage/triggers.py)

## Usage

### MCP Tools

```python
# Save a checkpoint
sage_save_checkpoint(
    core_question="How does the payment flow work?",
    thesis="Payments use Stripe with webhooks for confirmation...",
    confidence=0.8,
    key_evidence=[
        "PaymentIntent created before charging",
        "Webhook confirms settlement asynchronously"
    ],
    reasoning_trace="Started at the API endpoint, traced to Stripe...",
    open_questions=["How are refunds handled?"],
    auto_code_context=True  # Capture files from transcript (default)
)

# List checkpoints
sage_list_checkpoints(limit=10)

# Load a checkpoint into context
sage_load_checkpoint("2026-02-13T12-00-00_payment-flow")

# Search checkpoints semantically
sage_search_checkpoints("authentication patterns")
```

### Autosave

Checkpoints can be saved automatically:

```python
sage_autosave_check(
    trigger_event="synthesis",
    core_question="...",
    current_thesis="...",
    confidence=0.7,
    message_count=15,
    token_estimate=5000
)
```

### CLI

```bash
sage checkpoint list [--limit N] [--skill NAME]
sage checkpoint show <id>
sage checkpoint rm <id>
```

## Context Hydration

`key_evidence` and `reasoning_trace` help reconstruct your mental state when loading a checkpoint:

**Key Evidence** — Concrete facts you discovered:
```yaml
key_evidence:
  - "Tokens expire after 15 minutes"
  - "Refresh tokens are single-use"
  - "Signature uses RS256 not HS256"
```

**Reasoning Trace** — How you got there:
```yaml
reasoning_trace: |
  Started by searching for "token expiry". Found the constant in config.py.
  Then traced the refresh flow - was confused why refresh tokens are single-use.
  Realized it's for security: stolen refresh token only works once.
```

When restoring from checkpoint, these fields provide not just *what* you concluded, but *why* — which is crucial for continuing the work (or remembering what you learned).

## Deduplication

Checkpoints are deduplicated by thesis similarity:

1. Compute embedding of new checkpoint thesis
2. Compare to recent checkpoints
3. If similarity > 90%, skip saving
4. Configurable via `dedup_threshold`

This prevents saving the same conclusion repeatedly.

**Source:** [`sage/checkpoint.py:340-380`](../../sage/checkpoint.py)

## Depth Threshold

Prevents shallow checkpoints by requiring minimum conversation depth:

- `depth_min_messages`: Min messages (default: 8)
- `depth_min_tokens`: Min tokens (default: 2000)

Exempt triggers (bypass depth check):
- `manual` — User explicitly requested
- `precompact` — Critical for continuity
- `context_threshold` — At 70% context usage
- `research_start` — Initial state capture

## Code Context

Checkpoints automatically capture what code you explored:

```python
# Automatic (default)
sage_save_checkpoint(
    core_question="...",
    thesis="...",
    confidence=0.8
    # auto_code_context=True by default
)

# Response: "📍 Checkpoint saved [12 files changed]: ..."
```

See [Code Context Capture](./code-context.md) for details.

## Templates

Customize checkpoint format:

| Template | Purpose |
|----------|---------|
| `default` | Standard with all fields |
| `research` | Research-focused with sources emphasis |
| `decision` | Decision-focused with options/tradeoffs |
| `code-review` | Code review with files/changes |

```python
sage_save_checkpoint(
    core_question="...",
    thesis="...",
    confidence=0.8,
    template="decision"
)
```

## Storage

### Format

Markdown with YAML frontmatter (Obsidian-compatible):

```
~/.sage/checkpoints/
└── 2026-02-13T12-00-00_jwt-auth-research.md

<project>/.sage/checkpoints/
└── 2026-02-13T12-00-00_payment-flow.md
```

### Project-Local

Create `.sage/` in a project to store checkpoints locally:

```bash
cd my-project
mkdir .sage
# Now checkpoints save to my-project/.sage/checkpoints/
```

## Configuration

```yaml
# ~/.sage/tuning.yaml

# Deduplication
dedup_threshold: 0.90        # Thesis similarity threshold

# Depth requirements
depth_min_messages: 8        # Min messages before checkpoint
depth_min_tokens: 2000       # Min tokens before checkpoint

# Autosave thresholds
autosave_synthesis: 0.5      # Min confidence for synthesis trigger
autosave_topic_shift: 0.3    # Min confidence for topic shift
autosave_manual: 0.0         # Always save manual requests

# Maintenance
checkpoint_max_age_days: 90  # Prune older checkpoints
checkpoint_max_count: 200    # Max checkpoints to keep
```

## Learning Anti-Pattern

The checkpoint trap:

```
You: "Help me understand auth"
AI: [gives explanation]
You: "Checkpoint this"
```

This saves the AI's explanation, not your understanding.

The better pattern:

```
You: "Where is auth code?"
AI: [points to files]
You: [reads code, gets confused]
You: "I don't get why tokens aren't stored"
AI: [explains stateless design]
You: "Oh! Checkpoint this — I now understand because..."
```

Now your reasoning trace captures *your* learning journey, not just received information.

## Related

- [Code Context Capture](./code-context.md) — Automatic file tracking
- [Knowledge System](./knowledge.md) — Store reusable insights
- [Session Continuity](./continuity.md) — Survive compaction
- [Trigger Detection](./triggers.md) — Automatic checkpoint moments
