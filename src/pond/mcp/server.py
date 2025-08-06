"""
Pond MCP Server - FastMCP 2.0 implementation.

Exposes REST API endpoints as MCP tools with Jinja2 templating for responses.
"""

from pathlib import Path
from typing import Any
from pydantic import Field

import httpx
from fastmcp import FastMCP
from jinja2 import Environment, FileSystemLoader

from pond.mcp.config import get_settings
from pond.utils.time_service import TimeService

# Initialize FastMCP server
mcp = FastMCP(
    name="Pond Memory System",
    instructions="""
    This server provides semantic memory storage and retrieval for AI assistants.
    
    Available operations:
    - Store memories with automatic tagging and entity extraction
    - Search memories using semantic similarity and text matching
    - Retrieve recent memories within a time window
    - Initialize context with current time and recent memories
    - Check system and tenant health
    """
)

# Set up Jinja2 environment
template_dir = Path(__file__).parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(template_dir),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Initialize TimeService
time_service = TimeService()

# Settings will be lazy-loaded when needed
_settings = None

def get_config():
    """Get configuration settings (lazy-loaded)."""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


def format_age(dt_str: str) -> str:
    """Format an ISO datetime string as a relative age."""
    if not dt_str:
        return ""
    dt = time_service.parse_datetime(dt_str)
    return time_service.format_age(dt)


def format_datetime(dt_str: str) -> str:
    """Format an ISO datetime string as a human-readable datetime."""
    if not dt_str:
        return ""
    dt = time_service.parse_datetime(dt_str)
    return time_service.format_datetime(dt)


# Register the filters with Jinja2
jinja_env.filters['format_age'] = format_age
jinja_env.filters['format_datetime'] = format_datetime


async def make_request(method: str, endpoint: str, json: dict | None = None) -> dict:
    """Make an authenticated request to the Pond API."""
    config = get_config()
    url = f"{config.pond_url}/api/v1/{config.pond_tenant}/{endpoint}"
    headers = {"X-API-Key": config.pond_api_key} if config.pond_api_key else {}
    
    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "POST":
            response = await client.post(url, headers=headers, json=json or {})
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()


def render_template(template_name: str, data: dict[str, Any]) -> str:
    """Render a Jinja2 template with the given data."""
    template = jinja_env.get_template(template_name)
    return template.render(**data)


@mcp.tool(name="store")
async def store(content: str, tags: list[str] = Field(default_factory=list)) -> str:
    """
    Store a new memory with optional tags.
    
    The memory will be processed to extract entities, actions, and generate
    auto-tags. Returns the stored memory ID and any related memories (splash).
    """
    data = await make_request(
        "POST", 
        "store",
        {"content": content, "tags": tags}
    )
    return render_template("store.md.j2", data)


@mcp.tool(name="search")
async def search(query: str, limit: int = 10) -> str:
    """
    Search for memories using semantic similarity and text matching.
    
    The search uses a multiplex approach combining:
    - Full-text search
    - Entity/tag/action matching
    - Semantic similarity via embeddings
    """
    data = await make_request(
        "POST",
        "search",
        {"query": query, "limit": limit}
    )
    return render_template("search.md.j2", data)


@mcp.tool(name="recent")
async def recent(hours: float = 24.0, limit: int = 10) -> str:
    """
    Retrieve memories from the last N hours.
    
    Returns memories in reverse chronological order (newest first).
    """
    data = await make_request(
        "POST",
        "recent",
        {"hours": hours, "limit": limit}
    )
    return render_template("recent.md.j2", data)


@mcp.tool(name="init")
async def init() -> str:
    """
    Initialize context with current time and recent memories.
    
    This is typically called at the start of a conversation to establish
    temporal context and load relevant recent memories.
    """
    data = await make_request("POST", "init", {})
    return render_template("init.md.j2", data)


@mcp.tool(name="health")
async def health() -> str:
    """
    Check the health of the Pond system for the current tenant.
    
    Returns memory counts, embedding status, and date ranges.
    """
    # Get both system and tenant health
    system_health = await make_request("GET", "../health", None)
    
    # For tenant health, we need to adjust the URL
    config = get_config()
    url = f"{config.pond_url}/api/v1/{config.pond_tenant}/health"
    headers = {"X-API-Key": config.pond_api_key} if config.pond_api_key else {}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        tenant_health = response.json()
    
    return render_template("health.md.j2", {
        "system": system_health,
        "tenant": tenant_health
    })


if __name__ == "__main__":
    # Run the server with stdio transport (default)
    mcp.run()