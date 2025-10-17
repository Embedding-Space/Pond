"""
Entry point for running Pond Remote MCP server as a module.

This runs the MCP server with HTTP transport for remote access.

Usage:
    python -m pond.remote_mcp
    uv run python -m pond.remote_mcp
"""

from pond.remote_mcp.config import get_settings
from pond.remote_mcp.server import mcp

if __name__ == "__main__":
    config = get_settings()
    mcp.run(
        transport="http",
        host=config.http_host,
        port=config.http_port,
        path=config.http_path,
    )
