"""API key management for tenant authentication."""

import hashlib
import secrets
from datetime import UTC, datetime

from pond.infrastructure.database import DatabasePool


class APIKeyManager:
    """Manage API keys for tenants."""

    # Prefix for all API keys to make them identifiable
    KEY_PREFIX = "pond_sk_"
    KEY_LENGTH = 32  # Number of random bytes (will be longer in base64)

    def __init__(self, db_pool: DatabasePool):
        """Initialize with database pool."""
        self.db_pool = db_pool

    @staticmethod
    def generate_key() -> str:
        """Generate a new API key."""
        random_part = secrets.token_urlsafe(APIKeyManager.KEY_LENGTH)
        return f"{APIKeyManager.KEY_PREFIX}{random_part}"

    @staticmethod
    def hash_key(api_key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_key(self, tenant: str, description: str | None = None) -> str:
        """Create a new API key for a tenant.

        Returns:
            The API key (only shown once!)
        """
        api_key = self.generate_key()
        key_hash = self.hash_key(api_key)

        async with self.db_pool.acquire_tenant(tenant) as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (key_hash, description, active)
                VALUES ($1, $2, true)
                """,
                key_hash,
                description
                or f"API key created at {datetime.now(UTC).isoformat()}",
            )

        return api_key

    async def validate_key(self, api_key: str) -> str:
        """Validate an API key and return the tenant name if valid.

        This checks ALL tenant schemas to find which tenant owns the key.

        Returns:
            Tenant name if valid

        Raises:
            ValueError: If the API key is invalid or not found
        """
        if not api_key or not api_key.startswith(self.KEY_PREFIX):
            raise ValueError("Invalid API key format")

        key_hash = self.hash_key(api_key)

        # Get list of all tenants
        async with self.db_pool.acquire() as conn:
            from pond.infrastructure.schema import list_tenants

            tenants = await list_tenants(conn)

        # Check each tenant's api_keys table
        for tenant in tenants:
            async with self.db_pool.acquire_tenant(tenant) as conn:
                # Atomically update last_used and check if key exists in one operation
                # This avoids the race condition between SELECT and UPDATE
                update_result = await conn.execute(
                    """
                    UPDATE api_keys
                    SET last_used = NOW()
                    WHERE key_hash = $1 AND active = true
                    """,
                    key_hash,
                )

                # If we updated a row, the key exists and is active
                if update_result != "UPDATE 0":
                    return tenant

        raise ValueError("API key not found or inactive")

    async def rotate_key(self, tenant: str, old_api_key: str | None = None) -> str:
        """Create a new key and deactivate the old one.

        Args:
            tenant: Tenant name
            old_api_key: If provided, deactivate this specific key
                        If not provided, deactivate all active keys

        Returns:
            The new API key
        """
        async with self.db_pool.acquire_tenant(tenant) as conn:
            # Start a transaction
            async with conn.transaction():
                # Deactivate old key(s)
                if old_api_key:
                    key_hash = self.hash_key(old_api_key)
                    await conn.execute(
                        """
                        UPDATE api_keys
                        SET active = false
                        WHERE key_hash = $1
                        """,
                        key_hash,
                    )
                else:
                    # Deactivate all active keys
                    await conn.execute(
                        """
                        UPDATE api_keys
                        SET active = false
                        WHERE active = true
                        """
                    )

                # Create new key
                new_key = await self.create_key(tenant, "Rotated key")

        return new_key

    async def list_keys(self, tenant: str) -> list[dict]:
        """List all API keys for a tenant (without the actual keys).

        Returns:
            List of key metadata (id, description, created_at, last_used, active)
        """
        async with self.db_pool.acquire_tenant(tenant) as conn:
            rows = await conn.fetch(
                """
                SELECT id, description, created_at, last_used, active
                FROM api_keys
                ORDER BY created_at DESC
                """
            )
            return [dict(row) for row in rows]

    async def deactivate_key(self, tenant: str, key_id: int) -> bool:
        """Deactivate a specific key by ID.

        Returns:
            True if key was deactivated, False if not found
        """
        async with self.db_pool.acquire_tenant(tenant) as conn:
            result = await conn.execute(
                """
                UPDATE api_keys
                SET active = false
                WHERE id = $1 AND active = true
                """,
                key_id,
            )
            return result != "UPDATE 0"
