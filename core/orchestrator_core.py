#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from enum import Enum
from storage.storage_gateway import storage_gateway
from storage.postgres_adapter import postgres_adapter
from security.audit_logger import exir_boundary_tracer
from schemas_contract import (
    WorkOrderSchema, TaskOrderSchema, WorkHandoverSchema,
    MeetingMinutesHeaderSchema, EmergencyRequestSchema, StateRegistry
)

logger = logging.getLogger("exir_architecture_tracer")

class SagaState(Enum):
    """State machine for distributed saga transactions."""
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    COMPENSATING = "COMPENSATING"
    FAILED = "FAILED"

class WorkflowEvent(Enum):
    """Workflow events that trigger state transitions."""
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVISE = "REVISE"
    COMPLETE = "COMPLETE"
    CANCEL = "CANCEL"

class OrchestratorCore:
    """
    Central orchestration engine for document lifecycle management.
    Implements state machine, Saga pattern for compensating transactions, and sequence-based document numbering.
    """

    def __init__(self):
        self.saga_log: Dict[str, SagaState] = {}  # Track saga transactions by document ID

    # =========================================================================
    # SEQUENCE-BASED DOCUMENT NUMBER GENERATION
    # =========================================================================

    @exir_boundary_tracer
    async def generate_document_number(self, document_type: str) -> str:
        """
        Generate a human-readable document number using PostgreSQL sequences.
        """
        sequence_map = {
            "work_orders": "work_orders_seq",
            "task_orders": "task_orders_seq",
            "meeting_minutes": "meeting_minutes_seq",
            "emergency_requests": "emergency_requests_seq",
            "work_handovers": "work_handovers_seq"
        }
        
        sequence_name = sequence_map.get(document_type)
        if not sequence_name:
            raise ValueError(f"Unknown document type: {document_type}")
        
        # Get next sequence value from PostgreSQL
        seq_value = await postgres_adapter.get_next_sequence_value(sequence_name)
        
        # Map sequence to document prefix
        prefix_map = {
            "work_orders_seq": "WO-",
            "task_orders_seq": "TO-",
            "meeting_minutes_seq": "MOM-",
            "emergency_requests_seq": "EMG-",
            "work_handovers_seq": "HND-"
        }
        
        prefix = prefix_map.get(sequence_name, "DOC-")
        return f"{prefix}{seq_value}"

    # =========================================================================
    # WORK ORDER LIFECYCLE MANAGEMENT
    # =========================================================================

    @exir_boundary_tracer
    async def create_work_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new work order in DRAFT state.
        Generates document number via PostgreSQL sequence.
        """
        try:
            # Generate document number
            wo_number = await self.generate_document_number("work_orders")
            
            # Parse and validate schema
            schema = WorkOrderSchema(**data)
            
            # Prepare database record
            db_data = schema.model_dump(mode="json")
            db_data["wo_number"] = wo_number
            db_data["current_state"] = "DRAFT"
            db_data["id"] = uuid4()
            
            # Save to database
            result = await storage_gateway.save_entity("work_orders", db_data)
            
            # Log in audit trail
            await self._log_audit_event(
                result["id"],
                "WORK_ORDER",
                "STATE_CHANGE",
                f"Work order created in DRAFT state with number {wo_number}"
            )
            
            return result
        except Exception as e:
            logger.error(f"Failed to create work order: {e}")
            raise

    @exir_boundary_tracer
    async def transition_work_order_state(self, wo_id: UUID, event: WorkflowEvent, approver_id: UUID, comment: str = "") -> Dict[str, Any]:
        """
        Transition work order state based on workflow event.
        """
        # Fetch current work order
        wo = await storage_gateway.get_entity_by_id("work_orders", wo_id)
        if not wo:
            raise ValueError(f"Work order {wo_id} not found.")
        
        current_state = wo.get("current_state", "DRAFT")
        
        # Determine next state based on event
        next_state = await self._get_next_state(current_state, event, wo.get("current_state"))
        
        # Validate state transition
        if not await self._validate_state_transition(current_state, next_state, wo):
            raise ValueError(f"Invalid transition from {current_state} to {next_state}.")
        
        # Update approval fields based on event
        if event == WorkflowEvent.APPROVE:
            if current_state == "PLANT_MANAGER_REVIEW":
                wo["plant_manager_approved"] = True
                wo["plant_manager_opinion"] = comment
            elif current_state == "CEO_INITIAL_REVIEW":
                wo["ceo_initial_approved"] = True
                wo["ceo_initial_opinion"] = comment
            elif current_state == "CEO_FINAL_REVIEW":
                wo["ceo_final_approved"] = True
                wo["ceo_final_opinion"] = comment
        elif event == WorkflowEvent.REJECT:
            wo["current_state"] = "REJECTED"
            logger.info(f"Work order {wo_id} rejected. Resetting approvals.")
            # Reset all subsequent approvals
            if current_state in ("PLANT_MANAGER_REVIEW", "CEO_INITIAL_REVIEW"):
                wo["ceo_initial_approved"] = None
                wo["ceo_final_approved"] = None
        
        wo["current_state"] = next_state
        
        # Save updated work order
        result = await storage_gateway.save_entity("work_orders", wo)
        
        # Log audit event
        await self._log_audit_event(
            wo_id,
            "WORK_ORDER",
            "STATE_CHANGE",
            f"Transitioned from {current_state} to {next_state} via {event.value}. Comment: {comment}"
        )
        
        return result

    @exir_boundary_tracer
    async def _get_next_state(self, current_state: str, event: WorkflowEvent, approver_role: str) -> str:
        """Determine next state based on current state and event."""
        state_transitions = {
            "DRAFT": {
                WorkflowEvent.SUBMIT: "PLANT_MANAGER_REVIEW"
            },
            "PLANT_MANAGER_REVIEW": {
                WorkflowEvent.APPROVE: "CEO_INITIAL_REVIEW",
                WorkflowEvent.REJECT: "REJECTED"
            },
            "CEO_INITIAL_REVIEW": {
                WorkflowEvent.APPROVE: "HSE_REVIEW",
                WorkflowEvent.REJECT: "REJECTED"
            },
            "HSE_REVIEW": {
                WorkflowEvent.APPROVE: "ENGINEERING_REVIEW"
            },
            "ENGINEERING_REVIEW": {
                WorkflowEvent.APPROVE: "EXECUTOR_REVIEW"
            },
            "EXECUTOR_REVIEW": {
                WorkflowEvent.APPROVE: "WAREHOUSE_REVIEW"
            },
            "WAREHOUSE_REVIEW": {
                WorkflowEvent.APPROVE: "CEO_FINAL_REVIEW"
            },
            "CEO_FINAL_REVIEW": {
                WorkflowEvent.APPROVE: "APPROVED",
                WorkflowEvent.REJECT: "REJECTED"
            }
        }
        
        transitions = state_transitions.get(current_state, {})
        next_state = transitions.get(event)
        if not next_state:
            raise ValueError(f"No transition for {event.value} in state {current_state}")
        
        return next_state

    @exir_boundary_tracer
    async def _validate_state_transition(self, current_state: str, next_state: str, wo_data: Dict[str, Any]) -> bool:
        """Validate that state transition satisfies business rules."""
        # Rule 1: Cannot transition to APPROVED without all approvals
        if next_state == "APPROVED":
            if not (wo_data.get("plant_manager_approved") and
                    wo_data.get("ceo_initial_approved") and
                    wo_data.get("ceo_final_approved")):
                logger.warning("Cannot approve without all required signatures.")
                return False
        
        # Rule 2: Cannot transition from DRAFT to APPROVED directly
        if current_state == "DRAFT" and next_state not in ("PLANT_MANAGER_REVIEW", "REJECTED"):
            logger.warning("Draft work orders must go to plant manager first.")
            return False
        
        return True

    # =========================================================================
    # SAGA PATTERN FOR COMPENSATING TRANSACTIONS
    # =========================================================================

    @exir_boundary_tracer
    async def begin_saga_transaction(self, saga_id: str) -> None:
        """Start a saga transaction."""
        self.saga_log[saga_id] = SagaState.PENDING
        logger.info(f"Saga transaction {saga_id} started.")

    @exir_boundary_tracer
    async def commit_saga_step(self, saga_id: str, step_name: str, data: Dict[str, Any]) -> bool:
        """
        Execute a step in the saga and record it for potential rollback.
        """
        try:
            logger.info(f"Saga {saga_id}: Committing step {step_name}")
            # Step would save data here
            return True
        except Exception as e:
            logger.error(f"Saga step {step_name} failed: {e}")
            self.saga_log[saga_id] = SagaState.COMPENSATING
            await self.rollback_saga(saga_id)
            return False

    @exir_boundary_tracer
    async def rollback_saga(self, saga_id: str) -> None:
        """
        Rollback a failed saga by executing compensating transactions.
        E.g., if Directus write succeeded but PostgreSQL failed, delete from Directus.
        """
        logger.warning(f"Saga {saga_id}: Initiating compensating transactions (ROLLBACK).")
        self.saga_log[saga_id] = SagaState.FAILED
        
        # In production, maintain a log of committed steps and execute reversals
        # Example: if step 1 wrote to Directus, execute DELETE in Directus
        # This is where circuit breaker / retry logic applies

    # =========================================================================
    # TASK ORDER GENERATION FROM WORK ORDER
    # =========================================================================

    @exir_boundary_tracer
    async def create_task_order_from_work_order(self, wo_id: UUID, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a task order as a child of an approved work order.
        """
        # Verify work order exists and is approved
        wo = await storage_gateway.get_entity_by_id("work_orders", wo_id)
        if not wo or wo.get("current_state") != "APPROVED":
            raise ValueError(f"Work order {wo_id} must be in APPROVED state.")
        
        # Generate task order number
        to_number = await self.generate_document_number("task_orders")
        
        # Create task order
        schema = TaskOrderSchema(**task_data)
        db_data = schema.model_dump(mode="json")
        db_data["to_number"] = to_number
        db_data["parent_work_order_id"] = wo_id
        db_data["current_state"] = "CREATED"
        db_data["id"] = uuid4()
        
        result = await storage_gateway.save_entity("task_orders", db_data)
        
        await self._log_audit_event(
            result["id"],
            "TASK_ORDER",
            "STATE_CHANGE",
            f"Task order {to_number} created from work order {wo_id}"
        )
        
        return result

    # =========================================================================
    # HANDOVER & MATERIAL BALANCE VALIDATION
    # =========================================================================

    @exir_boundary_tracer
    async def finalize_work_handover(self, handover_id: UUID) -> Dict[str, Any]:
        """
        Finalize a work handover with strict material balance validation.
        """
        handover = await storage_gateway.get_entity_by_id("work_handovers", handover_id)
        if not handover:
            raise ValueError(f"Handover {handover_id} not found.")
        
        # Validate final status change
        if handover.get("final_status") != "FULLY_COMPLETED":
            # Perform material balance verification
            materials = handover.get("materials_balances", [])
            for mat in materials:
                qty_received = float(mat.get("qty_received_warehouse", 0))
                qty_used = float(mat.get("qty_actual_used", 0))
                qty_returned = float(mat.get("qty_returned_warehouse", 0))
                qty_waste = float(mat.get("qty_waste", 0))
                
                calculated_sum = qty_used + qty_returned + qty_waste
                if abs(qty_received - calculated_sum) > 0.0001:  # Allow tiny float error
                    raise ValueError(
                        f"Material balance mismatch for {mat.get('item_code_mesc')}: "
                        f"Received {qty_received}, but used+returned+waste = {calculated_sum}"
                    )
        
        handover["final_status"] = "FULLY_COMPLETED"
        result = await storage_gateway.save_entity("work_handovers", handover)
        
        await self._log_audit_event(
            handover_id,
            "HANDOVER",
            "STATE_CHANGE",
            "Work handover finalized and closed."
        )
        
        return result

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    @exir_boundary_tracer
    async def _log_audit_event(self, entity_id: UUID, entity_type: str, action_type: str, description: str) -> None:
        """Log an audit event for traceability."""
        audit_record = {
            "id": uuid4(),
            "entity_id": entity_id,
            "entity_type": entity_type,
            "action_type": action_type,
            "description": description,
            "user_id": None,  # Would be populated from context
            "timestamp": "NOW()"
        }
        
        try:
            await storage_gateway.save_entity("audit_logs", audit_record)
        except Exception as e:
            logger.warning(f"Could not log audit event: {e}")

# Global instance
orchestrator = OrchestratorCore()
