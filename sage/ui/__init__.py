"""Sage UI module.

Provides a local web interface and REST API for Sage data.
Designed as a fallback when CoWork/plugins aren't available.

Usage:
    sage ui              # Start web UI on localhost:5555
    sage ui --port 8080  # Custom port
    sage ui --api-only   # REST API only, no web UI
"""
