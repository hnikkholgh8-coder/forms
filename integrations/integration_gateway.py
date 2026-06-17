#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import httpx
from typing import Dict, Any, Optional, List
from schemas_contract import ProviderConfig
from security.audit_logger import exir_boundary_tracer

logger = logging.getLogger("exir_architecture_tracer")

class IntegrationGateway:
    """
    Manages integrations with external systems (Odoo, Vikunja, n8n, webhooks).
    Implements Circuit Breaker pattern for resilience.
    """

    def __init__(self):
        self.providers: Dict[str, ProviderConfig] = {}
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}

    def register_provider(self, config: ProviderConfig) -> None:
        """
        Register an external provider/integration.
        """
        provider_id = str(config.provider_id)
        self.providers[provider_id] = config
        # Initialize circuit breaker state
        self.circuit_breakers[provider_id] = {
            "state": "CLOSED",  # CLOSED, OPEN, HALF_OPEN
            "failure_count": 0,
            "failure_threshold": 5,
            "success_count": 0,
            "success_threshold": 3
        }
        logger.info(f"Registered provider: {config.name} ({provider_id})")

    @exir_boundary_tracer
    async def send_to_provider(self, provider_id: str, payload: Dict[str, Any]) -> bool:
        """
        Send a payload to an external provider with Circuit Breaker protection.
        """
        config = self.providers.get(provider_id)
        if not config or not config.is_active:
            logger.warning(f"Provider {provider_id} not found or inactive.")
            return False

        # Check circuit breaker state
        cb = self.circuit_breakers.get(provider_id, {})
        if cb.get("state") == "OPEN":
            logger.warning(f"Circuit breaker OPEN for {provider_id}. Rejecting request.")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if config.type == "odoo":
                    result = await self._send_to_odoo(client, config, payload)
                elif config.type == "vikunja":
                    result = await self._send_to_vikunja(client, config, payload)
                elif config.type == "n8n":
                    result = await self._send_to_n8n(client, config, payload)
                else:
                    result = await self._send_webhook(client, config, payload)

                if result:
                    # Success: update circuit breaker
                    cb["failure_count"] = 0
                    cb["success_count"] += 1
                    if cb["success_count"] >= cb["success_threshold"] and cb["state"] == "HALF_OPEN":
                        cb["state"] = "CLOSED"
                        cb["success_count"] = 0
                        logger.info(f"Circuit breaker CLOSED for {provider_id}.")
                    return True
                else:
                    raise Exception("Provider returned false.")
        except Exception as e:
            logger.error(f"Integration failure with {provider_id}: {e}")
            # Failure: update circuit breaker
            cb["failure_count"] = cb.get("failure_count", 0) + 1
            if cb["failure_count"] >= cb.get("failure_threshold", 5):
                cb["state"] = "OPEN"
                logger.warning(f"Circuit breaker OPEN for {provider_id}. Too many failures.")
            return False

    @exir_boundary_tracer
    async def _send_to_odoo(self, client: httpx.AsyncClient, config: ProviderConfig, payload: Dict[str, Any]) -> bool:
        """Send to Odoo RPC endpoint."""
        # Simplified mock implementation
        logger.info(f"Sending to Odoo: {payload}")
        return True

    @exir_boundary_tracer
    async def _send_to_vikunja(self, client: httpx.AsyncClient, config: ProviderConfig, payload: Dict[str, Any]) -> bool:
        """Send to Vikunja task management."""
        logger.info(f"Sending to Vikunja: {payload}")
        return True

    @exir_boundary_tracer
    async def _send_to_n8n(self, client: httpx.AsyncClient, config: ProviderConfig, payload: Dict[str, Any]) -> bool:
        """Send to n8n automation engine."""
        logger.info(f"Sending to n8n: {payload}")
        return True

    @exir_boundary_tracer
    async def _send_webhook(self, client: httpx.AsyncClient, config: ProviderConfig, payload: Dict[str, Any]) -> bool:
        """Send to generic webhook."""
        webhook_url = config.connection_params.get("url")
        if not webhook_url:
            logger.warning("Webhook URL not configured.")
            return False
        
        try:
            response = await client.post(webhook_url, json=payload)
            return response.status_code < 300
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False

# Global instance
integration_gateway = IntegrationGateway()
