# Sage UI

Sage provides multiple UI options - use whichever works for your environment.

## UI Options

| Option | When to Use | Command |
|--------|-------------|---------|
| **Local Web** | Works anywhere, offline | `sage ui` |
| **CoWork Plugin** | If you have CoWork access | Install plugin |
| **Obsidian** | Already use Obsidian | Open `~/.sage/` as vault |
| **CLI** | Quick checks | `sage checkpoint list` |
| **REST API** | Custom frontend | `sage ui --api-only` |

## Local Web UI

Zero-dependency local web interface.

```bash
sage ui                  # Start on http://localhost:5555
sage ui --port 8080      # Custom port
sage ui --no-browser     # Don't auto-open browser
```

### Features
- Browse checkpoints with search
- View knowledge items
- Click to see full details
- Works offline
- Dark mode by default

### Screenshots

```
┌──────────────────────────────────────────────────────┐
│  Sage Research Memory             Checkpoints: 42    │
│                                   Knowledge: 15      │
├──────────────────────────────────────────────────────┤
│  [Checkpoints]  [Knowledge]                          │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ authentication-flow              85%          │   │
│  │ JWT tokens with refresh rotation...           │   │
│  │ Feb 14 · synthesis                            │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ rate-limiting-design             70%          │   │
│  │ Sliding window algorithm for login...         │   │
│  │ Feb 13 · branch_point                         │   │
│  └──────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

## REST API

For building custom frontends or integrations.

```bash
sage ui --api-only       # API only, no web UI
```

### Endpoints

#### Health
```
GET /api/health
```
Returns checkpoint/knowledge counts and config status.

#### Checkpoints
```
GET /api/checkpoints              # List all
GET /api/checkpoints?limit=10     # Limit results
GET /api/checkpoints/:id          # Get by ID
GET /api/checkpoints/search?q=jwt # Search
```

#### Knowledge
```
GET    /api/knowledge             # List all
GET    /api/knowledge/:id         # Get by ID
GET    /api/knowledge/recall?q=   # Recall matching
POST   /api/knowledge             # Add new
PUT    /api/knowledge/:id         # Update
DELETE /api/knowledge/:id         # Remove
```

#### Config
```
GET /api/config                   # Get current config
```

### Example: Custom Frontend

```javascript
// Fetch checkpoints
const res = await fetch('http://localhost:5555/api/checkpoints');
const { checkpoints } = await res.json();

// Search
const search = await fetch('http://localhost:5555/api/checkpoints/search?q=auth');
const { results } = await search.json();

// Add knowledge
await fetch('http://localhost:5555/api/knowledge', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    id: 'my-insight',
    content: 'Something I learned...',
    keywords: ['learning', 'insight'],
  }),
});
```

## CoWork Plugin

See [cowork-plugin.md](cowork-plugin.md) for CoWork/Claude Desktop integration.

## Obsidian

Sage checkpoints are Markdown with YAML frontmatter - Obsidian-compatible.

1. Open Obsidian
2. Open folder as vault: `~/.sage/checkpoints/` or `.sage/checkpoints/`
3. Browse, search, and edit checkpoints

Works great with:
- Obsidian's graph view (see checkpoint relationships)
- Backlinks (find related checkpoints)
- Search (full-text across all checkpoints)
- Templates (create checkpoint templates)

## Bring Your Own UI

The Sage data model is simple:

```
~/.sage/
├── checkpoints/
│   └── *.md              # Markdown + YAML frontmatter
├── knowledge/
│   ├── index.yaml        # Knowledge registry
│   └── *.md              # Knowledge content
└── tuning.yaml           # Config
```

Build any UI you want:
- Read checkpoints: Parse Markdown + YAML
- Read knowledge: Parse `index.yaml` + content files
- Use API: `sage ui --api-only` for REST endpoints
- Use MCP: Connect to `sage-mcp` server directly
