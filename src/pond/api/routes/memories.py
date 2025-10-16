"""Memory management API endpoints."""

import pendulum
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel

from pond.api.dependencies import get_repository
from pond.api.models import (
    InitRequest,
    InitResponse,
    MemoryResponse,
    RecentRequest,
    RecentResponse,
    SearchRequest,
    SearchResponse,
    StoreRequest,
    StoreResponse,
)
from pond.domain.repository import MemoryRepository
from pond.metrics import (
    memories_stored,
    memory_store_duration,
    search_duration,
    searches_performed,
)

logger = structlog.get_logger()

router = APIRouter(
    tags=["memories"],
)


@router.post("/store", response_model=StoreResponse)
async def store_memory(
    store_request: StoreRequest,
    request: Request,
    repository: MemoryRepository = Depends(get_repository),  # noqa: B008
) -> StoreResponse:
    """Store a new memory and return related memories (splash).

    The splash contains semantically similar memories (0.7-0.9 similarity)
    to help maintain context.
    """
    try:
        # Get tenant from authenticated request
        tenant = request.state.tenant

        # Store the memory with metrics tracking
        logger.info(
            "storing_memory",
            tenant=tenant,
            content_length=len(store_request.content),
            tag_count=len(store_request.tags),
        )

        with memory_store_duration.labels(tenant=tenant).time():
            memory, splash_memories = await repository.store(
                tenant=tenant,
                content=store_request.content,
                user_tags=store_request.tags,
            )

        # Increment the stored memories counter
        memories_stored.labels(tenant=tenant).inc()

        logger.info(
            "memory_stored",
            tenant=tenant,
            memory_id=memory.id,
            splash_count=len(splash_memories),
        )

        # Convert to response models
        splash_response = [MemoryResponse.from_memory(m) for m in splash_memories]

        return StoreResponse(
            id=memory.id or 0,  # Should never be None after storage
            splash=splash_response,
        )

    except ValueError as e:
        # Validation errors from the repository
        logger.warning(
            "store_validation_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        # Unexpected errors
        logger.exception(
            "store_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store memory",
        ) from e


@router.post("/search", response_model=SearchResponse)
async def search_memories(
    search_request: SearchRequest,
    request: Request,
    repository: MemoryRepository = Depends(get_repository),  # noqa: B008
) -> SearchResponse:
    """Search memories or return recent memories if no query.

    Empty query returns recent memories (last 24 hours by default).
    Non-empty query uses unified search across text, features, and semantics.
    """
    try:
        # Get tenant from authenticated request
        tenant = request.state.tenant
        search_type = "recent" if not search_request.query else "semantic"

        with search_duration.labels(tenant=tenant, type=search_type).time():
            if not search_request.query:
                # Empty query - return recent memories
                logger.info(
                    "fetching_recent_memories",
                    tenant=tenant,
                    limit=search_request.limit,
                )

                # Get memories from last 24 hours
                from datetime import timedelta

                from pond.utils.time_service import TimeService

                time_service = TimeService()
                since = time_service.now() - timedelta(hours=24)

                memories = await repository.get_recent(
                    tenant=tenant,
                    since=since,
                    limit=search_request.limit,
                )

                logger.info(
                    "recent_memories_fetched",
                    tenant=tenant,
                    count=len(memories),
                )
            else:
                # Search with query
                logger.info(
                    "searching_memories",
                    tenant=tenant,
                    query=search_request.query,
                    limit=search_request.limit,
                )

                memories = await repository.search(
                    tenant=tenant,
                    query=search_request.query,
                    limit=search_request.limit,
                )

                logger.info(
                    "search_completed",
                    tenant=tenant,
                    query=search_request.query,
                    result_count=len(memories),
                )

        # Increment search counter
        searches_performed.labels(tenant=tenant, type=search_type).inc()

        # Convert to response models
        memory_responses = [MemoryResponse.from_memory(m) for m in memories]

        return SearchResponse(
            memories=memory_responses,
            count=len(memory_responses),
        )

    except ValueError as e:
        # Validation errors
        logger.warning(
            "search_validation_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        # Unexpected errors
        logger.exception(
            "search_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search memories",
        ) from e


@router.post("/recent", response_model=RecentResponse)
async def get_recent_memories(
    recent_request: RecentRequest,
    request: Request,
    repository: MemoryRepository = Depends(get_repository),  # noqa: B008
) -> RecentResponse:
    """Get recent memories within a time window.

    Returns memories from the last N hours (default 24).
    """
    try:
        # Get tenant from authenticated request
        tenant = request.state.tenant

        from datetime import timedelta

        from pond.utils.time_service import TimeService

        # Calculate the time window
        time_service = TimeService()
        hours = recent_request.hours if recent_request.hours else 24
        since = time_service.now() - timedelta(hours=hours)

        logger.info(
            "fetching_recent_memories",
            tenant=tenant,
            hours=hours,
            limit=recent_request.limit,
        )

        # Get recent memories with metrics tracking
        with search_duration.labels(tenant=tenant, type="recent").time():
            memories = await repository.get_recent(
                tenant=tenant,
                since=since,
                limit=recent_request.limit,
            )

        # Track this as a recent search
        searches_performed.labels(tenant=tenant, type="recent").inc()

        logger.info(
            "recent_memories_fetched",
            tenant=tenant,
            count=len(memories),
        )

        # Convert to response models
        memory_responses = [MemoryResponse.from_memory(m) for m in memories]

        return RecentResponse(
            memories=memory_responses,
            count=len(memory_responses),
        )

    except ValueError as e:
        # Validation errors
        logger.warning(
            "recent_validation_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        # Unexpected errors
        logger.exception(
            "recent_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recent memories",
        ) from e


@router.post("/init", response_model=InitResponse)
async def initialize_context(
    init_request: InitRequest,
    request: Request,
    repository: MemoryRepository = Depends(get_repository),  # noqa: B008
) -> InitResponse:
    """Initialize context with current time and recent memories.

    This endpoint is designed for AI assistants to get their initial context.
    Returns the current time (for temporal awareness) and recent memories.
    """
    try:
        # Get tenant from authenticated request
        tenant = request.state.tenant

        from datetime import timedelta

        from pond.utils.time_service import TimeService

        # Get current time
        time_service = TimeService()
        current_time = time_service.now()

        # Get recent memories (last 24 hours, up to 10)
        since = current_time - timedelta(hours=24)

        logger.info(
            "initializing_context",
            tenant=tenant,
        )

        memories = await repository.get_recent(
            tenant=tenant,
            since=since,
            limit=10,  # Default to 10 recent memories for init
        )

        logger.info(
            "context_initialized",
            tenant=tenant,
            memory_count=len(memories),
        )

        # Convert to response models
        memory_responses = [MemoryResponse.from_memory(m) for m in memories]

        return InitResponse(
            current_time=current_time,
            recent_memories=memory_responses,
        )

    except Exception as e:
        # Unexpected errors
        tenant_name = tenant if 'tenant' in locals() else 'unknown'
        logger.exception(
            "init_error",
            tenant=tenant_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize context",
        ) from e


class VectorsRequest(BaseModel):
    """Request for fetching vectors."""
    limit: int = 6000

@router.post("/vectors")
async def get_vectors(
    request: Request,
    body: VectorsRequest = Body(...),  # noqa: B008
) -> dict:
    """Get memories with embeddings for 3D visualization.

    Returns the most recent memories with their 768-dimensional embeddings
    for use in THE VISUALIZER. The tenant is determined by the API key.
    """
    repository: MemoryRepository = request.app.state.memory_repository

    # Get tenant from the authenticated API key - this was set by AuthenticationMiddleware
    tenant = request.state.tenant
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authenticated tenant",
        )

    try:
        logger.info(
            "fetching_vectors",
            tenant=tenant,
            limit=body.limit,
        )

        # Get recent memories with embeddings
        memories = await repository.get_recent(
            tenant=tenant,
            since=pendulum.now("UTC").subtract(years=1),  # Last year of memories
            limit=body.limit,
        )

        # Filter to only memories with embeddings and format for visualization
        vectors = []
        for memory in memories:
            if memory.embedding is not None:
                vectors.append({
                    "id": memory.id,
                    "content": memory.content,
                    "embedding": memory.embedding.tolist(),
                    "created_at": memory.metadata.get("created_at"),
                })

        logger.info(
            "vectors_fetched",
            tenant=tenant,
            count=len(vectors),
        )

        return {"memories": vectors}

    except Exception as e:
        logger.exception(
            "vectors_error",
            tenant=tenant,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch vectors",
        ) from e
