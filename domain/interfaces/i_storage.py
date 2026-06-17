#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID
from security.audit_logger import exir_boundary_tracer

class IStorageProvider(ABC):
    """
    Abstract Storage Provider Interface.
    Decouples domain/orchestration layer from the direct database operations (Directus / PostgreSQL).
    """

    @abstractmethod
    async def save_entity(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Asynchronously save an entity in the database.
        Must support inserting new records or updating existing ones.
        """
        pass

    @abstractmethod
    async def get_entity_by_id(self, table_name: str, entity_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Asynchronously retrieve an entity by its UUID.
        """
        pass

    @abstractmethod
    async def list_entities(self, table_name: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Asynchronously retrieve a list of entities matching filters, excluding soft-deleted ones.
        """
        pass
