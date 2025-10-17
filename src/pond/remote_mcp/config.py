"""
Configuration for Pond MCP Server using Pydantic Settings.
"""

from functools import lru_cache

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class MCPSettings(BaseSettings):
    """Settings for the Pond MCP server."""

    model_config = ConfigDict(
        # NO env_file - all config comes from MCP client via environment
        case_sensitive=False
    )

    # Pond API settings
    pond_url: str = Field(
        default="http://pond:8000", description="URL of the Pond API server"
    )
    pond_api_key: str = Field(
        ..., description="API key for authenticating with Pond (determines tenant)"
    )

    # HTTP server settings
    http_host: str = Field(
        default="0.0.0.0", description="Host to bind HTTP server to"
    )
    http_port: int = Field(default=8080, description="Port for HTTP server")
    http_path: str = Field(default="/mcp", description="Path for MCP endpoint")


@lru_cache
def get_settings() -> MCPSettings:
    """Get settings singleton - lazy loaded when first accessed."""
    return MCPSettings()
