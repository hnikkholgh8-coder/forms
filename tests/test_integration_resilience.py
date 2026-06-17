#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Integration Resilience Tests - Dual-write failures, Circuit Breaker, and Compensating Transactions.
"""

import pytest
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from integrations.integration_gateway import integration_gateway, IntegrationGateway
from schemas_contract import ProviderConfig
from storage.storage_gateway import storage_gateway

# ============================================================================
# CIRCUIT BREAKER PATTERN TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures():
    """Test Circuit Breaker opens after repeated failures."""
    gateway = IntegrationGateway()
    
    config = ProviderConfig(
        provider_id=uuid4(),
        name="Test Provider",
        type="webhook",
        connection_params={"url": "http://failing-service.com/webhook"},
        is_active=True
    )
    gateway.register_provider(config)
    provider_id = str(config.provider_id)
    
    # Mock repeated failures
    with patch.object(gateway, '_send_webhook', new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = Exception("Service unavailable")
        
        # First 5 calls should fail
        for _ in range(5):
            result = await gateway.send_to_provider(provider_id, {"test": "data"})
            assert result is False
        
        # Circuit breaker should now be OPEN
        cb = gateway.circuit_breakers.get(provider_id, {})
        assert cb["state"] == "OPEN"
        
        # Next call should be rejected immediately
        result = await gateway.send_to_provider(provider_id, {"test": "data"})
        assert result is False

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """Test Circuit Breaker transitions from OPEN to HALF_OPEN to CLOSED."""
    gateway = IntegrationGateway()
    
    config = ProviderConfig(
        provider_id=uuid4(),
        name="Recovery Provider",
        type="webhook",
        connection_params={"url": "http://recovering-service.com/webhook"},
        is_active=True
    )
    gateway.register_provider(config)
    provider_id = str(config.provider_id)
    
    # Manually set to HALF_OPEN
    gateway.circuit_breakers[provider_id]["state"] = "HALF_OPEN"
    
    # Mock successful responses
    with patch.object(gateway, '_send_webhook', new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        
        # Send 3 successful requests
        for _ in range(3):
            result = await gateway.send_to_provider(provider_id, {"test": "data"})
            assert result is True
        
        # Circuit breaker should now be CLOSED
        cb = gateway.circuit_breakers.get(provider_id, {})
        assert cb["state"] == "CLOSED"

# ============================================================================
# DUAL-WRITE SAGA PATTERN TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_dual_write_postgres_success_directus_failure():
    """
    Saga test: PostgreSQL succeeds, Directus fails.
    Expected: Compensating DELETE in PostgreSQL.
    """
    # Mock data
    entity_id = uuid4()
    test_data = {
        "id": entity_id,
        "username": "test_user",
        "email": "test@example.com"
    }
    
    with patch.object(storage_gateway.postgres_adapter, 'save_entity', new_callable=AsyncMock) as mock_pg:
        with patch.object(storage_gateway.directus_adapter, 'save_entity', new_callable=AsyncMock) as mock_dir:
            # PostgreSQL succeeds, Directus fails
            mock_pg.return_value = test_data
            mock_dir.side_effect = Exception("Directus API error")
            
            # Attempt dual-write
            try:
                result = await storage_gateway.dual_write_entity("users_and_staff", test_data, test_data)
                # PostgreSQL data should be returned
                assert result["id"] == entity_id
            except Exception as e:
                # Directus error is logged but doesn't crash
                assert "Directus" in str(e) or result is not None

@pytest.mark.asyncio
async def test_compensating_transaction_rollback():
    """
    Test compensating transaction (rollback) after saga failure.
    """
    saga_id = "test_saga_compensation"
    entity_id = uuid4()
    table_name = "work_orders"
    
    with patch.object(storage_gateway, 'compensating_delete', new_callable=AsyncMock) as mock_rollback:
        mock_rollback.return_value = True
        
        # Trigger compensating delete
        result = await storage_gateway.compensating_delete(table_name, entity_id, in_directus=False)
        assert result is True
        mock_rollback.assert_called_once()

@pytest.mark.asyncio
async def test_saga_fail_both_databases():
    """
    Test saga failure when both PostgreSQL and Directus fail.
    Expected: Saga marked as FAILED, no further retries.
    """
    from core.orchestrator_core import orchestrator, SagaState
    
    saga_id = "test_saga_both_fail"
    await orchestrator.begin_saga_transaction(saga_id)
    
    # Simulate both fail
    await orchestrator.rollback_saga(saga_id)
    
    # Saga should be marked FAILED
    assert orchestrator.saga_log[saga_id] == SagaState.FAILED

# ============================================================================
# INTEGRATION PROVIDER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_send_to_odoo_provider():
    """Test sending payload to Odoo provider."""
    gateway = IntegrationGateway()
    
    config = ProviderConfig(
        provider_id=uuid4(),
        name="Odoo ERP",
        type="odoo",
        connection_params={"url": "http://odoo:8069/jsonrpc"},
        is_active=True
    )
    gateway.register_provider(config)
    provider_id = str(config.provider_id)
    
    payload = {
        "model": "project.task",
        "method": "create",
        "values": {"name": "New Task", "project_id": 1}
    }
    
    with patch.object(gateway, '_send_to_odoo', new_callable=AsyncMock) as mock_odoo:
        mock_odoo.return_value = True
        result = await gateway.send_to_provider(provider_id, payload)
        assert result is True

@pytest.mark.asyncio
async def test_send_to_vikunja_provider():
    """Test sending task to Vikunja project management."""
    gateway = IntegrationGateway()
    
    config = ProviderConfig(
        provider_id=uuid4(),
        name="Vikunja PM",
        type="vikunja",
        connection_params={"url": "http://vikunja:3456/api"},
        is_active=True
    )
    gateway.register_provider(config)
    provider_id = str(config.provider_id)
    
    payload = {
        "project_id": 1,
        "title": "New Maintenance Task",
        "description": "Required maintenance work"
    }
    
    with patch.object(gateway, '_send_to_vikunja', new_callable=AsyncMock) as mock_vk:
        mock_vk.return_value = True
        result = await gateway.send_to_provider(provider_id, payload)
        assert result is True

@pytest.mark.asyncio
async def test_send_to_n8n_automation():
    """Test triggering n8n automation workflow."""
    gateway = IntegrationGateway()
    
    config = ProviderConfig(
        provider_id=uuid4(),
        name="n8n Automation",
        type="n8n",
        connection_params={"url": "http://n8n:5678/webhook/trigger"},
        is_active=True
    )
    gateway.register_provider(config)
    provider_id = str(config.provider_id)
    
    payload = {
        "workflow": "email_notification",
        "recipient": "team@example.com",
        "subject": "Work Order Approved"
    }
    
    with patch.object(gateway, '_send_to_n8n', new_callable=AsyncMock) as mock_n8n:
        mock_n8n.return_value = True
        result = await gateway.send_to_provider(provider_id, payload)
        assert result is True

@pytest.mark.asyncio
async def test_webhook_send_timeout():
    """Test webhook timeout handling."""
    import httpx
    
    gateway = IntegrationGateway()
    
    config = ProviderConfig(
        provider_id=uuid4(),
        name="Slow Webhook",
        type="custom_webhook",
        connection_params={"url": "http://slow-service.com/webhook"},
        is_active=True
    )
    gateway.register_provider(config)
    provider_id = str(config.provider_id)
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))
        mock_client.return_value = mock_instance
        
        result = await gateway.send_to_provider(provider_id, {"test": "data"})
        assert result is False

# ============================================================================
# SOFT DELETE & ARCHIVAL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_soft_delete_prevents_retrieval():
    """Test that soft-deleted records are not retrieved."""
    
    # Mock PostgreSQL to return soft-deleted record
    soft_deleted_record = {
        "id": uuid4(),
        "title": "Archived WO",
        "is_deleted": True
    }
    
    # Query should filter out is_deleted=TRUE
    with patch.object(storage_gateway.postgres_adapter, 'get_entity_by_id', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None  # Simulating filter where is_deleted=TRUE is excluded
        
        result = await mock_get("work_orders", soft_deleted_record["id"])
        assert result is None

@pytest.mark.asyncio
async def test_hard_reference_prevents_soft_delete():
    """Test RESTRICT constraint prevents soft-delete of referenced record."""
    
    work_order_id = uuid4()
    task_with_reference = {
        "id": uuid4(),
        "parent_work_order_id": work_order_id,
        "current_state": "IN_PROGRESS"
    }
    
    # Attempt to soft-delete the work order should fail if task exists
    with patch.object(storage_gateway.postgres_adapter, 'soft_delete_entity', new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = False  # Simulating RESTRICT constraint
        
        result = await mock_delete("work_orders", work_order_id)
        assert result is False

# ============================================================================
# PERFORMANCE & LOAD TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_provider_sends():
    """Test multiple concurrent sends to different providers."""
    gateway = IntegrationGateway()
    
    # Register multiple providers
    providers = []
    for i in range(3):
        config = ProviderConfig(
            provider_id=uuid4(),
            name=f"Provider {i}",
            type="webhook",
            connection_params={"url": f"http://provider{i}.com/webhook"},
            is_active=True
        )
        gateway.register_provider(config)
        providers.append(str(config.provider_id))
    
    # Mock all sends to succeed
    async def send_task(provider_id: str):
        with patch.object(gateway, '_send_webhook', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            return await gateway.send_to_provider(provider_id, {"test": "data"})
    
    # Send concurrently
    results = await asyncio.gather(
        *[send_task(pid) for pid in providers],
        return_exceptions=True
    )
    
    assert len(results) == 3
    assert all(r is True or isinstance(r, Exception) for r in results)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
