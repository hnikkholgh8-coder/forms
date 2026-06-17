#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Exir Pooyan Smart Management System - FastAPI Entry Point.
Production-grade REST API with async/await, comprehensive error handling, and observability.
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from security.audit_logger import exir_boundary_tracer
from security.auth_manager import auth_manager
from storage.postgres_adapter import postgres_adapter
from storage.directus_adapter import directus_adapter
from core.orchestrator_core import orchestrator

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# Lifespan Management
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: startup and shutdown handlers.
    """
    # ========== STARTUP ==========
    logger.info("🚀 Starting Exir Pooyan Smart Management System...")
    
    try:
        # Initialize database adapters
        await postgres_adapter.initialize()
        logger.info("✅ PostgreSQL adapter initialized")
        
        await directus_adapter.initialize()
        logger.info("✅ Directus adapter initialized")
        
        # Bootstrap authentication
        await auth_manager.bootstrap_roles()
        logger.info("✅ Keycloak roles bootstrapped")
        
        logger.info("✅ All services initialized successfully")
    except Exception as e:
        logger.error(f"❌ Startup failed: {str(e)}")
        raise
    
    yield
    
    # ========== SHUTDOWN ==========
    logger.info("🛑 Shutting down Exir Pooyan...")
    
    try:
        if postgres_adapter.pool:
            await postgres_adapter.pool.close()
            logger.info("✅ PostgreSQL pool closed")
        
        if directus_adapter.client:
            await directus_adapter.client.aclose()
            logger.info("✅ Directus client closed")
        
        logger.info("✅ Graceful shutdown complete")
    except Exception as e:
        logger.error(f"❌ Shutdown error: {str(e)}")

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Exir Pooyan Smart Management System",
    description="Enterprise Iranian industrial management platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ============================================================================
# CORS Configuration
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure per environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Request/Response Models
# ============================================================================

class HealthResponse(BaseModel):
    status: str
    version: str
    components: Dict[str, str]

class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int

# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check endpoint"
)
@exir_boundary_tracer
async def health_check() -> Dict[str, Any]:
    """
    System health status.
    
    Returns:
        - status: HEALTHY/DEGRADED/CRITICAL
        - version: API version
        - components: Status of each service
    """
    components = {
        "postgres": "ready" if postgres_adapter.pool else "not_initialized",
        "directus": "ready" if directus_adapter.client else "not_initialized",
        "keycloak": "ready",  # Checked on each auth call
    }
    
    any_down = any(v != "ready" for v in components.values())
    status = "DEGRADED" if any_down else "HEALTHY"
    
    return {
        "status": status,
        "version": "1.0.0",
        "components": components,
    }

@app.get("/", tags=["System"], summary="Root API info")
@exir_boundary_tracer
async def root() -> Dict[str, str]:
    """API root with documentation links."""
    return {
        "message": "Exir Pooyan Smart Management System API",
        "docs": "/api/docs",
        "redoc": "/api/redoc",
        "openapi": "/api/openapi.json",
    }

# ============================================================================
# Work Order Endpoints
# ============================================================================

@app.post(
    "/api/v1/work-orders",
    tags=["Work Orders"],
    summary="Create work order"
)
@exir_boundary_tracer
async def create_work_order(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create new work order.
    
    Args:
        data: Work order creation payload
    
    Returns:
        Created work order with generated wo_number
    """
    try:
        wo = await orchestrator.create_work_order(data)
        return {
            "success": True,
            "data": wo,
        }
    except Exception as e:
        logger.error(f"Work order creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

@app.get(
    "/api/v1/work-orders/{wo_id}",
    tags=["Work Orders"],
    summary="Get work order"
)
@exir_boundary_tracer
async def get_work_order(wo_id: str) -> Dict[str, Any]:
    """
    Retrieve work order by ID.
    
    Args:
        wo_id: Work order UUID
    
    Returns:
        Work order details
    """
    try:
        wo = await orchestrator.storage.get_entity_by_id("work_orders", wo_id)
        if not wo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Work order {wo_id} not found",
            )
        return {"success": True, "data": wo}
    except Exception as e:
        logger.error(f"Work order retrieval failed: {str(e)}")
        raise

# ============================================================================
# Task Order Endpoints
# ============================================================================

@app.post(
    "/api/v1/task-orders",
    tags=["Task Orders"],
    summary="Create task order from work order"
)
@exir_boundary_tracer
async def create_task_order(wo_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create task order linked to work order.
    
    Args:
        wo_id: Parent work order UUID
        data: Task order creation payload
    
    Returns:
        Created task order with generated to_number
    """
    try:
        to = await orchestrator.create_task_order_from_work_order(wo_id, data)
        return {"success": True, "data": to}
    except Exception as e:
        logger.error(f"Task order creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

# ============================================================================
# State Transition Endpoints
# ============================================================================

@app.post(
    "/api/v1/work-orders/{wo_id}/transition",
    tags=["Work Orders"],
    summary="Transition work order state"
)
@exir_boundary_tracer
async def transition_state(
    wo_id: str,
    event: str,
    approver_id: str,
    comment: str = "",
) -> Dict[str, Any]:
    """
    Transition work order to next state based on event.
    
    Args:
        wo_id: Work order UUID
        event: Workflow event (SUBMIT, APPROVE, REJECT, REVISE, COMPLETE, CANCEL)
        approver_id: User UUID performing transition
        comment: Optional approval comment
    
    Returns:
        Updated work order with new state
    """
    try:
        wo = await orchestrator.transition_work_order_state(
            wo_id=wo_id,
            event=event,
            approver_id=approver_id,
            comment=comment,
        )
        return {"success": True, "data": wo}
    except Exception as e:
        logger.error(f"State transition failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
@exir_boundary_tracer
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with standardized format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Error",
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )

@app.exception_handler(Exception)
@exir_boundary_tracer
async def general_exception_handler(request, exc: Exception):
    """Handle unhandled exceptions gracefully."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred",
            "status_code": 500,
        },
    )

# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
