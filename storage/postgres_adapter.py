#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
import asyncpg
from domain.interfaces.i_storage import IStorageProvider
from security.audit_logger import exir_boundary_tracer

logger = logging.getLogger("exir_architecture_tracer")

# Configuration from environment
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")
PG_DATABASE = os.getenv("PG_DATABASE", "exir_pooyan")

class PostgresAdapter(IStorageProvider):
    """
    Direct PostgreSQL adapter for domain entities.
    Implements thread-safe connection pooling and async/await patterns.
    """

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    @exir_boundary_tracer
    async def initialize(self) -> None:
        """Initialize connection pool to PostgreSQL."""
        try:
            self.pool = await asyncpg.create_pool(
                host=PG_HOST,
                port=PG_PORT,
                user=PG_USER,
                password=PG_PASSWORD,
                database=PG_DATABASE,
                min_size=5,
                max_size=20,
            )
            logger.info("PostgreSQL connection pool initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise

    @exir_boundary_tracer
    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed.")

    @exir_boundary_tracer
    async def save_entity(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save (insert/update) an entity in PostgreSQL.
        Returns the full record including database-generated values.
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized.")
        
        async with self.pool.acquire() as conn:
            # Check if record exists (if ID is provided)
            entity_id = data.get("id")
            if entity_id:
                existing = await conn.fetchrow(f"SELECT id FROM {table_name} WHERE id = $1 AND is_deleted = FALSE", entity_id)
                if existing:
                    # Update existing
                    columns = []
                    values = []
                    idx = 1
                    for k, v in data.items():
                        if k != "id":
                            columns.append(f"{k} = ${idx}")
                            values.append(v)
                            idx += 1
                    values.append(entity_id)
                    
                    query = f"UPDATE {table_name} SET {', '.join(columns)}, date_updated = NOW() WHERE id = ${idx} RETURNING *"
                    result = await conn.fetchrow(query, *values)
                    return dict(result) if result else data
            
            # Insert new
            columns = list(data.keys())
            placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
            column_list = ", ".join(columns)
            query = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders}) RETURNING *"
            
            result = await conn.fetchrow(query, *data.values())
            return dict(result) if result else data

    @exir_boundary_tracer
    async def get_entity_by_id(self, table_name: str, entity_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Retrieve an entity by ID, excluding soft-deleted records.
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized.")
        
        async with self.pool.acquire() as conn:
            query = f"SELECT * FROM {table_name} WHERE id = $1 AND is_deleted = FALSE"
            result = await conn.fetchrow(query, entity_id)
            return dict(result) if result else None

    @exir_boundary_tracer
    async def list_entities(self, table_name: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Retrieve a list of entities, applying optional filters. Always excludes soft-deleted.
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized.")
        
        async with self.pool.acquire() as conn:
            query = f"SELECT * FROM {table_name} WHERE is_deleted = FALSE"
            params = []
            
            if filters:
                for key, value in filters.items():
                    query += f" AND {key} = ${len(params) + 1}"
                    params.append(value)
            
            results = await conn.fetch(query, *params)
            return [dict(row) for row in results]

    @exir_boundary_tracer
    async def soft_delete_entity(self, table_name: str, entity_id: UUID) -> bool:
        """
        Soft-delete an entity by setting is_deleted to TRUE.
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized.")
        
        async with self.pool.acquire() as conn:
            query = f"UPDATE {table_name} SET is_deleted = TRUE, date_updated = NOW() WHERE id = $1"
            result = await conn.execute(query, entity_id)
            return result == "UPDATE 1"

    @exir_boundary_tracer
    async def get_next_sequence_value(self, sequence_name: str) -> str:
        """
        Retrieve the next value from a PostgreSQL sequence for document numbers.
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized.")
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(f"SELECT nextval('{sequence_name}');")
            return str(result)

# Global instance
postgres_adapter = PostgresAdapter()
