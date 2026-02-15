"""REST API for Sage data.

Exposes Sage functionality over HTTP for any frontend to consume.
Uses Python's built-in http.server for zero dependencies.

Endpoints:
    GET  /api/health              - Health check
    GET  /api/checkpoints         - List checkpoints
    GET  /api/checkpoints/:id     - Get checkpoint details
    GET  /api/checkpoints/search?q=  - Search checkpoints
    GET  /api/knowledge           - List knowledge items
    GET  /api/knowledge/:id       - Get knowledge item
    GET  /api/knowledge/recall?q= - Recall matching knowledge
    POST /api/knowledge           - Add knowledge item
    PUT  /api/knowledge/:id       - Update knowledge item
    DELETE /api/knowledge/:id     - Remove knowledge item
    GET  /api/config              - Get current config
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


def serialize(obj: Any) -> Any:
    """Serialize dataclasses and other objects to JSON-compatible format."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, Path):
        return str(obj)
    return obj


class SageAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Sage REST API."""

    # Will be set by server
    project_path: Path | None = None

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send JSON response."""
        body = json.dumps(serialize(data), indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        """Send error response."""
        self._send_json({"error": message}, status)

    def _get_query_params(self) -> dict[str, str]:
        """Parse query parameters."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        return {k: v[0] for k, v in params.items()}

    def _get_path_parts(self) -> list[str]:
        """Get path parts after /api/."""
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        if path.startswith("api/"):
            path = path[4:]
        return path.split("/") if path else []

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        parts = self._get_path_parts()
        params = self._get_query_params()

        if not parts:
            self._send_json({"status": "ok", "version": "3.2.0"})
            return

        # Route to handlers
        resource = parts[0]

        if resource == "health":
            self._handle_health()
        elif resource == "checkpoints":
            self._handle_checkpoints_get(parts[1:], params)
        elif resource == "knowledge":
            self._handle_knowledge_get(parts[1:], params)
        elif resource == "config":
            self._handle_config_get()
        else:
            self._send_error(404, f"Unknown resource: {resource}")

    def do_POST(self) -> None:
        """Handle POST requests."""
        parts = self._get_path_parts()

        if parts[0] == "knowledge":
            self._handle_knowledge_post()
        else:
            self._send_error(404, f"Cannot POST to: {parts[0]}")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        parts = self._get_path_parts()

        if parts[0] == "knowledge" and len(parts) > 1:
            self._handle_knowledge_put(parts[1])
        else:
            self._send_error(404, f"Cannot PUT to: {'/'.join(parts)}")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        parts = self._get_path_parts()

        if parts[0] == "knowledge" and len(parts) > 1:
            self._handle_knowledge_delete(parts[1])
        else:
            self._send_error(404, f"Cannot DELETE: {'/'.join(parts)}")

    # =========================================================================
    # Handlers
    # =========================================================================

    def _handle_health(self) -> None:
        """GET /api/health"""
        from sage.checkpoint import list_checkpoints
        from sage.config import get_sage_config
        from sage.knowledge import list_knowledge

        config = get_sage_config(self.project_path)
        checkpoints = list_checkpoints(project_path=self.project_path)
        knowledge = list_knowledge(project_path=self.project_path)

        self._send_json({
            "status": "ok",
            "checkpoints": len(checkpoints),
            "knowledge": len(knowledge),
            "config": {
                "output_format": config.output_format,
                "embedding_model": config.embedding_model,
            },
        })

    def _handle_checkpoints_get(self, parts: list[str], params: dict[str, str]) -> None:
        """GET /api/checkpoints, /api/checkpoints/:id, /api/checkpoints/search"""
        from sage.checkpoint import (
            format_checkpoint_for_context,
            list_checkpoints,
            load_checkpoint,
            search_checkpoints,
        )

        if not parts:
            # List all
            limit = int(params.get("limit", "50"))
            checkpoints = list_checkpoints(limit=limit, project_path=self.project_path)
            self._send_json({
                "checkpoints": [
                    {
                        "id": cp.id,
                        "thesis": cp.thesis[:100] + "..." if len(cp.thesis) > 100 else cp.thesis,
                        "confidence": cp.confidence,
                        "trigger": cp.trigger,
                        "ts": cp.ts,
                    }
                    for cp in checkpoints
                ],
                "total": len(checkpoints),
            })
        elif parts[0] == "search":
            # Search
            query = params.get("q", "")
            if not query:
                self._send_error(400, "Missing query parameter 'q'")
                return
            results = search_checkpoints(query, limit=10, project_path=self.project_path)
            self._send_json({
                "query": query,
                "results": [
                    {"id": cp.id, "thesis": cp.thesis, "score": score}
                    for cp, score in results
                ],
            })
        else:
            # Get by ID
            checkpoint_id = parts[0]
            checkpoint = load_checkpoint(checkpoint_id, project_path=self.project_path)
            if checkpoint:
                self._send_json({
                    "checkpoint": checkpoint,
                    "formatted": format_checkpoint_for_context(checkpoint),
                })
            else:
                self._send_error(404, f"Checkpoint not found: {checkpoint_id}")

    def _handle_knowledge_get(self, parts: list[str], params: dict[str, str]) -> None:
        """GET /api/knowledge, /api/knowledge/:id, /api/knowledge/recall"""
        from sage.knowledge import (
            format_recalled_context,
            get_knowledge,
            list_knowledge,
            recall_knowledge,
        )

        if not parts:
            # List all
            items = list_knowledge(project_path=self.project_path)
            self._send_json({
                "knowledge": [
                    {
                        "id": item.id,
                        "triggers": list(item.triggers),
                        "type": item.item_type,
                        "scope": item.scope,
                    }
                    for item in items
                ],
                "total": len(items),
            })
        elif parts[0] == "recall":
            # Recall
            query = params.get("q", "")
            if not query:
                self._send_error(400, "Missing query parameter 'q'")
                return
            result = recall_knowledge(query, project_path=self.project_path)
            self._send_json({
                "query": query,
                "items": result.items,
                "total_tokens": result.total_tokens,
                "formatted": format_recalled_context(result),
            })
        else:
            # Get by ID
            knowledge_id = parts[0]
            item = get_knowledge(knowledge_id, project_path=self.project_path)
            if item:
                self._send_json({"knowledge": item})
            else:
                self._send_error(404, f"Knowledge not found: {knowledge_id}")

    def _handle_knowledge_post(self) -> None:
        """POST /api/knowledge - Add new knowledge."""
        from sage.knowledge import add_knowledge

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error(400, f"Invalid JSON: {e}")
            return

        required = ["id", "content", "keywords"]
        missing = [f for f in required if f not in body]
        if missing:
            self._send_error(400, f"Missing required fields: {missing}")
            return

        result = add_knowledge(
            knowledge_id=body["id"],
            content=body["content"],
            keywords=body["keywords"],
            skill=body.get("skill"),
            source=body.get("source", ""),
            item_type=body.get("type", "knowledge"),
            project_path=self.project_path,
        )

        if result.is_ok():
            self._send_json({"status": "created", "id": body["id"]}, 201)
        else:
            self._send_error(400, str(result.err()))

    def _handle_knowledge_put(self, knowledge_id: str) -> None:
        """PUT /api/knowledge/:id - Update knowledge."""
        from sage.knowledge import update_knowledge

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error(400, f"Invalid JSON: {e}")
            return

        result = update_knowledge(
            knowledge_id=knowledge_id,
            content=body.get("content"),
            keywords=body.get("keywords"),
            status=body.get("status"),
            source=body.get("source"),
            project_path=self.project_path,
        )

        if result.is_ok():
            self._send_json({"status": "updated", "id": knowledge_id})
        else:
            self._send_error(400, str(result.err()))

    def _handle_knowledge_delete(self, knowledge_id: str) -> None:
        """DELETE /api/knowledge/:id - Remove knowledge."""
        from sage.knowledge import remove_knowledge

        result = remove_knowledge(knowledge_id, project_path=self.project_path)

        if result.is_ok():
            self._send_json({"status": "deleted", "id": knowledge_id})
        else:
            self._send_error(404, str(result.err()))

    def _handle_config_get(self) -> None:
        """GET /api/config"""
        from sage.config import get_sage_config

        config = get_sage_config(self.project_path)
        self._send_json({"config": config.to_dict()})

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging, use our logger."""
        logger.debug(f"{self.address_string()} - {format % args}")
