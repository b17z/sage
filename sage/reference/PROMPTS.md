# Prompt Engineering Patterns

Effective patterns for AI interactions.

## Query Formulation

### Specific Over Vague
- Bad: "tell me about privacy"
- Good: "ZK-KYC implementation patterns for stealth addresses"

### 2-5 Word Searches
Web search works best with focused queries:
- "Aztec mainnet launch date"
- "EIP-5564 stealth addresses"
- "Coinbase attestations API"

### Iterative Refinement
Start broad, then narrow based on results:
1. "stealth address privacy" (understand landscape)
2. "stealth address attestation gap" (specific problem)
3. "ZKPassport stealth address" (specific solution)

## Output Structure

### Lead with Findings
Don't bury the lede. Start with conclusions, then evidence.

### Cite Sources
Include URLs for web-sourced claims.

### Acknowledge Uncertainty
Flag when information is:
- Outdated (check date)
- Contested (multiple viewpoints)
- Incomplete (gaps in sources)

## Persona Patterns

### Expert Persona
"You are a specialized research expert focused on [domain]..."

### Multi-Perspective Review
Invoke multiple viewpoints:
- Security engineer: "What attack vectors exist?"
- Product manager: "Does this solve user problems?"
- Data engineer: "How does this scale?"

## Research Mode Instructions

```markdown
### Phase 1: Initial Exploration
- Search for foundational information (2-3 queries)
- Identify key sources and perspectives

### Phase 2: Gap Analysis
- What questions remain unanswered?
- What claims need verification?

### Phase 3: Targeted Follow-up
- Search to fill specific gaps
- Verify claims against primary sources

### Phase 4: Synthesis
- Lead with key findings
- Support with evidence and citations
- End with open questions
```
