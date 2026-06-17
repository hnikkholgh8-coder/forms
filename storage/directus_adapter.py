#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import httpx
from typing import Dict, Any, Optional, List
from uuid import UUID
from domain.interfaces.i_storage import IStorageProvider
from security.audit_logger import exir_boundary_tracer

logger = logging.getLogger("exir_architecture_tracer")

# Configuration from environment
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "http://localhost:8055")
DIRECTUS_ADMIN_TOKEN = os.getenv("DIRECTUS_ADMIN_TOKEN", "test-admin-token")

class DirectusAdapter(IStorageProvider):
    """
    Directus BaaS adapter for user/role management and file attachment handling.
    Provides async HTTP interactions with the Directus REST API.
    """

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.admin_token = DIRECTUS_ADMIN_TOKEN

    @exir_boundary_tracer
    async def initialize(self) -> None:
        """Initialize the HTTP client for Directus communication."""
        self.client = httpx.AsyncClient(
            base_url=DIRECTUS_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        logger.info("Directus adapter initialized.")

    @exir_boundary_tracer
    async def close(self) -> None:
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            logger.info("Directus adapter client closed.")

    @exir_boundary_tracer
    async def save_entity(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save an entity to Directus (primarily users and role assignments).
        """
        if not self.client:
            raise RuntimeError("Directus adapter not initialized.")
        
        entity_id = data.get("id")
        
        try:
            if entity_id:
                # Update existing
                response = await self.client.patch(
                    f"/items/{table_name}/{entity_id}",
                    json=data
                )
                if response.status_code in (200, 204):
                    return data
                else:
                    logger.warning(f"Directus update failed: {response.status_code}")
                    return data
            else:
                # Create new
                response = await self.client.post(
                    f"/items/{table_name}",
                    json=data
                )
                if response.status_code in (200, 201):
                    result = response.json()
                    return result.get("data", data)
                else:
                    logger.warning(f"Directus create failed: {response.status_code}")
                    return data
        except Exception as e:
            logger.error(f"Directus save_entity error: {e}")
            # Resilience: return data as-is
            return data

    @exir_boundary_tracer
    async def get_entity_by_id(self, table_name: str, entity_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Retrieve an entity from Directus by ID.
        """
        if not self.client:
            raise RuntimeError("Directus adapter not initialized.")
        
        try:
            response = await self.client.get(f"/items/{table_name}/{entity_id}")
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {})
            return None
        except Exception as e:
            logger.error(f"Directus get_entity_by_id error: {e}")
            return None

    @exir_boundary_tracer
    async def list_entities(self, table_name: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        List entities from Directus.
        """
        if not self.client:
            raise RuntimeError("Directus adapter not initialized.")
        
        try:
            params = {"limit": 1000}
            if filters:
                # Basic filter support
                filter_rules = []
                for key, value in filters.items():
                    filter_rules.append(f"{key}[_eq]={value}")
                if filter_rules:
                    params["filter"] = "&".join(filter_rules)
            
            response = await self.client.get(f"/items/{table_name}", params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            return []
        except Exception as e:
            logger.error(f"Directus list_entities error: {e}")
            return []

    @exir_boundary_tracer
    async def upload_file(self, file_path: str) -> Optional[str]:
        """
        Upload a file to Directus files storage.
        Returns the file UUID on success.
        """
        if not self.client:
            raise RuntimeError("Directus adapter not initialized.")
        
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                response = await self.client.post("/files", files=files)
                if response.status_code in (200, 201):
                    data = response.json()
                    return data.get("data", {}).get("id")
        except Exception as e:
            logger.error(f"Directus file upload error: {e}")
        
        return None

    @exir_boundary_tracer
    async def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from Directus storage.
        """
        if not self.client:
            raise RuntimeError("Directus adapter not initialized.")
        
        try:
            response = await self.client.delete(f"/files/{file_id}")
            return response.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Directus delete_file error: {e}")
            return False

# Global instance
directus_adapter = DirectusAdapter()
