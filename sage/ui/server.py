"""Local web server for Sage UI.

Serves both the REST API and a static web interface.
Zero external dependencies - uses Python's built-in http.server.

Usage:
    from sage.ui.server import run_server
    run_server(port=5555)
"""

from __future__ import annotations

import logging
import mimetypes
import threading
import webbrowser
from http.server import HTTPServer
from pathlib import Path

from sage.ui.api import SageAPIHandler

logger = logging.getLogger(__name__)

# Static files directory (relative to this file)
STATIC_DIR = Path(__file__).parent / "static"


class SageUIHandler(SageAPIHandler):
    """Combined handler for API and static files."""

    static_dir: Path = STATIC_DIR

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        """Handle GET - route to API or serve static files."""
        if self.path.startswith("/api/"):
            super().do_GET()
        else:
            self._serve_static()

    def _serve_static(self) -> None:
        """Serve static files."""
        # Parse path
        path = self.path.split("?")[0].strip("/")
        if not path:
            path = "index.html"

        file_path = self.static_dir / path

        # Security: prevent directory traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(self.static_dir.resolve())):
                self._send_error(403, "Forbidden")
                return
        except (ValueError, RuntimeError):
            self._send_error(400, "Invalid path")
            return

        # Check file exists
        if not file_path.exists() or not file_path.is_file():
            # SPA fallback - serve index.html for client-side routing
            file_path = self.static_dir / "index.html"
            if not file_path.exists():
                self._send_error(404, "Not found")
                return

        # Serve file
        try:
            content = file_path.read_bytes()
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error(f"Error serving {file_path}: {e}")
            self._send_error(500, "Internal server error")


def create_handler(project_path: Path | None = None, static_dir: Path | None = None):
    """Create a handler class with project path and static dir bound."""

    class BoundHandler(SageUIHandler):
        pass

    BoundHandler.project_path = project_path
    BoundHandler.static_dir = static_dir or STATIC_DIR
    return BoundHandler


def run_server(
    port: int = 5555,
    project_path: Path | None = None,
    static_dir: Path | None = None,
    open_browser: bool = True,
    api_only: bool = False,
) -> None:
    """Run the Sage web server.

    Args:
        port: Port to listen on
        project_path: Project root for project-scoped data
        static_dir: Directory with static files (default: built-in)
        open_browser: Open browser on start
        api_only: Only serve API, no static files
    """
    handler = create_handler(project_path, static_dir)

    if api_only:
        # Use base API handler without static file serving
        handler = SageAPIHandler
        handler.project_path = project_path

    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, handler)

    url = f"http://localhost:{port}"
    mode = "API only" if api_only else "Web UI + API"

    print(f"Sage {mode} running at {url}")
    print(f"Project: {project_path or 'global (~/.sage)'}")
    print("Press Ctrl+C to stop")

    if open_browser and not api_only:
        # Open browser after a short delay
        def open_delayed():
            import time
            time.sleep(0.5)
            webbrowser.open(url)

        threading.Thread(target=open_delayed, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()


def run_server_background(
    port: int = 5555,
    project_path: Path | None = None,
) -> HTTPServer:
    """Run server in background thread. Returns server instance.

    Useful for testing or embedding in other apps.
    Call server.shutdown() to stop.
    """
    handler = create_handler(project_path)
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, handler)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    logger.info(f"Sage server running in background at http://localhost:{port}")
    return httpd
