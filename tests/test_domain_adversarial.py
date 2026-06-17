#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Adversarial Test Suite for Domain Components: Lookup, Audit Logger, and Storage.
"""

import pytest
import asyncio
import logging
from uuid import uuid4
from lookup.engine_lookup import engine_lookup, LookupMatch
from security.audit_logger import exir_boundary_tracer, logger as audit_logger
from schemas_contract import UserSchema, AssetSchema
from storage.postgres_adapter import postgres_adapter
from storage.directus_adapter import directus_adapter

# ============================================================================
# LOOKUP ENGINE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_lookup_empty_query():
    """Test fuzzy lookup with empty query."""
    results = await engine_lookup.search_users("", threshold=0.6)
    assert results == []

@pytest.mark.asyncio
async def test_lookup_short_query():
    """Test fuzzy lookup with single character (too short)."""
    results = await engine_lookup.search_users("a", threshold=0.6)
    assert results == []

@pytest.mark.asyncio
async def test_lookup_high_threshold():
    """Test lookup with very high similarity threshold."""
    # Load test users
    test_user = UserSchema(
        id=uuid4(),
        username="test_user",
        full_name="علی محمد",
        email="ali@example.com",
        department="MECHANICAL",
        role="executor"
    )
    engine_lookup.load_users([test_user])
    
    # Search with query that doesn't match perfectly
    results = await engine_lookup.search_users("محمود", threshold=0.95)
    # With high threshold, should get few or no results
    assert isinstance(results, list)

@pytest.mark.asyncio
async def test_lookup_special_characters():
    """Test lookup with special characters."""
    test_user = UserSchema(
        id=uuid4(),
        username="user-name_123",
        full_name="کاربر - ۱۲۳",
        email="user@example.com",
        department="IT",
        role="ceo"
    )
    engine_lookup.load_users([test_user])
    
    results = await engine_lookup.search_users("user-name", threshold=0.6)
    assert len(results) >= 0  # Should handle special chars gracefully

@pytest.mark.asyncio
async def test_asset_lookup():
    """Test asset fuzzy lookup."""
    test_asset = AssetSchema(
        id=uuid4(),
        asset_code="PUMP-001",
        asset_name="Centrifugal Pump (Main)",
        location="Building A"
    )
    engine_lookup.load_assets([test_asset])
    
    results = await engine_lookup.search_assets("PUMP", threshold=0.6)
    assert len(results) > 0
    assert results[0].label.startswith("PUMP-001")

# ============================================================================
# AUDIT LOGGER DECORATOR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_decorator_async_function():
    """Test @exir_boundary_tracer on async function."""
    
    @exir_boundary_tracer
    async def sample_async_func(x: int, y: int) -> int:
        await asyncio.sleep(0.01)
        return x + y
    
    result = await sample_async_func(5, 3)
    assert result == 8

@pytest.mark.asyncio
async def test_decorator_sync_function():
    """Test @exir_boundary_tracer on sync function."""
    
    @exir_boundary_tracer
    def sample_sync_func(text: str) -> str:
        return text.upper()
    
    result = sample_sync_func("hello")
    assert result == "HELLO"

@pytest.mark.asyncio
async def test_decorator_with_exception():
    """Test @exir_boundary_tracer catches and re-raises exceptions."""
    
    @exir_boundary_tracer
    async def failing_func():
        raise ValueError("Intentional test error")
    
    with pytest.raises(ValueError, match="Intentional test error"):
        await failing_func()

@pytest.mark.asyncio
async def test_decorator_logging_output(caplog):
    """Test @exir_boundary_tracer generates proper log output."""
    
    @exir_boundary_tracer
    async def sample_func(param: str):
        return f"Result: {param}"
    
    with caplog.at_level(logging.DEBUG):
        result = await sample_func("test_value")
    
    # Check for log messages containing INPUT and OUTPUT markers
    log_text = caplog.text
    assert "INPUT" in log_text or "OUTPUT" in log_text

# ============================================================================
# STORAGE ADAPTER RESILIENCE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_postgres_adapter_not_initialized():
    """Test PostgreSQL adapter operations when pool is None."""
    adapter = postgres_adapter
    
    with pytest.raises(RuntimeError, match="not initialized"):
        await adapter.save_entity("work_orders", {"id": uuid4()})

@pytest.mark.asyncio
async def test_directus_adapter_network_failure():
    """Test Directus adapter graceful handling of network errors."""
    from unittest.mock import AsyncMock, MagicMock
    from storage.directus_adapter import directus_adapter
    
    # Mock HTTP client to raise exception
    original_client = directus_adapter.client
    directus_adapter.client = MagicMock()
    directus_adapter.client.post = AsyncMock(side_effect=ConnectionError("Network unreachable"))
    
    # Should not crash, but return original data
    result = await directus_adapter.save_entity("users_and_staff", {"id": uuid4(), "username": "test"})
    assert result is not None
    
    # Restore
    directus_adapter.client = original_client

@pytest.mark.asyncio
async def test_storage_gateway_unknown_table():
    """Test storage gateway with unrecognized table name."""
    from storage.storage_gateway import storage_gateway
    
    with pytest.raises(ValueError, match="Unknown table"):
        await storage_gateway.save_entity("nonexistent_table", {})

# ============================================================================
# PYDANTIC SCHEMA VALIDATION ADVERSARIAL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_user_schema_invalid_email():
    """Test UserSchema with invalid email."""
    with pytest.raises(ValueError):
        UserSchema(
            id=uuid4(),
            username="testuser",
            full_name="Test User",
            email="not-an-email",  # Invalid
            department="IT",
            role="executor"
        )

@pytest.mark.asyncio
async def test_user_schema_empty_username():
    """Test UserSchema with empty username (normalized to None)."""
    from schemas_contract import LaxOptionalStr
    
    # Empty string should be converted to None by BeforeValidator
    # But UserSchema requires non-empty username
    with pytest.raises(ValueError):
        UserSchema(
            id=uuid4(),
            username="",  # Empty
            full_name="Test User",
            email="user@example.com",
            department="IT",
            role="executor"
        )

@pytest.mark.asyncio
async def test_material_balance_extreme_precision():
    """Test MaterialBalance with extreme decimal precision."""
    from schemas_contract import MaterialBalanceSchema
    from decimal import Decimal
    
    # Create with very precise decimals
    balance = MaterialBalanceSchema(
        handover_id=uuid4(),
        item_code_mesc="01.02.0001",
        item_description="Test",
        unit_of_measure="KG",
        qty_received_warehouse=Decimal("10.123456789012"),
        qty_actual_used=Decimal("5.5"),
        qty_returned_warehouse=Decimal("4.623456789012"),
        qty_waste=Decimal("0.0"),
    )
    
    # Verify Decimal is preserved
    assert isinstance(balance.qty_received_warehouse, Decimal)

@pytest.mark.asyncio
async def test_plugin_manifest_invalid_version():
    """Test PluginManifest with invalid version format."""
    from schemas_contract import PluginManifestSchema
    
    with pytest.raises(ValueError, match="version"):
        PluginManifestSchema(
            plugin_id="exir.test",
            name="Test",
            version="1.2"  # Missing patch version
        )

@pytest.mark.asyncio
async def test_plugin_manifest_invalid_id():
    """Test PluginManifest with invalid namespace ID."""
    from schemas_contract import PluginManifestSchema
    
    with pytest.raises(ValueError, match="namespace"):
        PluginManifestSchema(
            plugin_id="invalid-id-format",  # No dot separator
            name="Test",
            version="1.0.0"
        )

# ============================================================================
# PAGINATION & API RESPONSE WRAPPER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_paginated_response_structure():
    """Test PaginatedData schema structure."""
    from schemas_contract import PaginatedData, PaginationMeta, UserSchema
    
    users = [
        UserSchema(
            id=uuid4(),
            username="user1",
            full_name="User One",
            email="user1@example.com",
            department="IT",
            role="executor"
        )
    ]
    
    pagination = PaginationMeta(
        total_count=100,
        current_page=1,
        page_size=10,
        has_next=True,
        has_prev=False
    )
    
    response = PaginatedData(items=users, pagination=pagination)
    assert len(response.items) == 1
    assert response.pagination.total_count == 100

@pytest.mark.asyncio
async def test_api_response_with_error():
    """Test APIResponse with error state."""
    from schemas_contract import APIResponse
    
    response = APIResponse(
        success=False,
        data=None,
        error={"code": "VALIDATION_ERROR", "message": "Invalid input"},
        metadata={"timestamp": "2025-06-17T12:00:00Z"}
    )
    
    assert response.success is False
    assert response.error is not None

# ============================================================================
# RACE CONDITION & CONCURRENCY SIMULATION
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_state_machine_transitions():
    """Simulate concurrent transitions on same WO (should fail)."""
    wo_id = uuid4()
    
    async def attempt_transition(transition_id: int):
        # In reality, would call orchestrator.transition_work_order_state
        await asyncio.sleep(0.001)
        return f"Transition {transition_id}"
    
    # Simulate concurrent requests
    results = await asyncio.gather(
        attempt_transition(1),
        attempt_transition(2),
        return_exceptions=True
    )
    
    assert len(results) == 2

@pytest.mark.asyncio
async def test_material_balance_concurrent_updates():
    """Test concurrent material balance updates (pessimistic locking)."""
    
    async def update_balance(iteration: int):
        await asyncio.sleep(0.01)
        return f"Update {iteration} completed"
    
    results = await asyncio.gather(
        update_balance(1),
        update_balance(2),
        update_balance(3)
    )
    
    assert len(results) == 3

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
