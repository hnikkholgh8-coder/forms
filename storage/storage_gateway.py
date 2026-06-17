#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
from domain.interfaces.i_storage import IStorageProvider
from storage.postgres_adapter import postgres_adapter
from storage.directus_adapter import directus_adapter
from security.audit_logger import exir_boundary_tracer

logger = logging.getLogger("exir_architecture_tracer")

class StorageGateway:
    """
    Intelligent storage gateway that routes operations to appropriate adapter.
    Implements the Ignorance Hierarchy: upper layers don't know about underlying databases.
    """

    # Tables stored in PostgreSQL (domain-specific operational data)
    POSTGRES_TABLES = {
        "work_orders", "task_orders", "emergency_requests", "meeting_minutes",
        "meeting_items", "meeting_attendees", "work_handovers", "material_balances",
        "quality_checklists", "audit_logs", "assets"
    }

    # Tables stored in Directus (user/role/attachment management)
    DIRECTUS_TABLES = {"users_and_staff", "plugin_manifests"}

    @exir_boundary_tracer
    async def save_entity(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route save operation to appropriate storage backend.
        """
        if table_name in self.POSTGRES_TABLES:
            return await postgres_adapter.save_entity(table_name, data)
        elif table_name in self.DIRECTUS_TABLES:
            return await directus_adapter.save_entity(table_name, data)
        else:
            raise ValueError(f"Unknown table: {table_name}")

    @exir_boundary_tracer
    async def get_entity_by_id(self, table_name: str, entity_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Route retrieval operation to appropriate storage backend.
        """
        if table_name in self.POSTGRES_TABLES:
            return await postgres_adapter.get_entity_by_id(table_name, entity_id)
        elif table_name in self.DIRECTUS_TABLES:
            return await directus_adapter.get_entity_by_id(table_name, entity_id)
        else:
            raise ValueError(f"Unknown table: {table_name}")

    @exir_boundary_tracer
    async def list_entities(self, table_name: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Route list operation to appropriate storage backend.
        """
        if table_name in self.POSTGRES_TABLES:
            return await postgres_adapter.list_entities(table_name, filters)
        elif table_name in self.DIRECTUS_TABLES:
            return await directus_adapter.list_entities(table_name, filters)
        else:
            raise ValueError(f"Unknown table: {table_name}")

    @exir_boundary_tracer
    async def soft_delete_entity(self, table_name: str, entity_id: UUID) -> bool:
        """
        Soft-delete an entity (only PostgreSQL supports this pattern).
        """
        if table_name in self.POSTGRES_TABLES:
            return await postgres_adapter.soft_delete_entity(table_name, entity_id)
        else:
            logger.warning(f"Soft-delete not supported for table {table_name}")
            return False

    @exir_boundary_tracer
    async def dual_write_entity(self, table_name: str, pg_data: Dict[str, Any], directus_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Dual-write pattern: write to both PostgreSQL and Directus (if applicable).
        This is used for critical user/document synchronization.
        """
        # Write to primary storage
        pg_result = await postgres_adapter.save_entity(table_name, pg_data)
        
        # If Directus data provided, also write there
        if directus_data:
            try:
                await directus_adapter.save_entity(table_name, directus_data)
            except Exception as e:
                logger.error(f"Directus dual-write failed: {e}. PostgreSQL already committed.")
        
        return pg_result

    @exir_boundary_tracer
    async def compensating_delete(self, table_name: str, entity_id: UUID, in_directus: bool = False) -> bool:
        """
        Compensating transaction: delete a record in case of dual-write failure.
        Used in Saga pattern for rollback.
        """
        if in_directus:
            try:
                response = await directus_adapter.client.delete(f"/items/{table_name}/{entity_id}")
                return response.status_code in (200, 204)
            except Exception as e:
                logger.error(f"Compensating Directus delete failed: {e}")
                return False
        else:
            return await postgres_adapter.soft_delete_entity(table_name, entity_id)

# Global instance
storage_gateway = StorageGateway()
