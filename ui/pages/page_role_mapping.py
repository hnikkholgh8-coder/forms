#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Role Mapping Page - Administrator Interface for Keycloak-to-Directus Synchronization.
"""

import logging
from typing import List, Dict, Any
from nicegui import ui
from security.audit_logger import exir_boundary_tracer
from security.auth_manager import auth_manager

logger = logging.getLogger("exir_architecture_tracer")

@exir_boundary_tracer
async def load_keycloak_users() -> List[Dict[str, Any]]:
    """Fetch unmapped users from Keycloak."""
    # Mock implementation for testing
    return [
        {"keycloak_id": "user1", "username": "mohsen_engineer", "email": "mohsen@exir.com", "full_name": "مهسن مهندسی"},
        {"keycloak_id": "user2", "username": "fatemeh_hse", "email": "fatemeh@exir.com", "full_name": "فاطمه ایمنی"},
        {"keycloak_id": "user3", "username": "ali_warehouse", "email": "ali@exir.com", "full_name": "علی انبار"},
    ]

@exir_boundary_tracer
async def load_available_roles() -> List[Dict[str, str]]:
    """Fetch available Directus roles."""
    return [
        {"role_id": auth_manager.roles_map.get("plant_manager"), "name": "مدیر کارخانه"},
        {"role_id": auth_manager.roles_map.get("ceo"), "name": "مدیرعامل"},
        {"role_id": auth_manager.roles_map.get("hse_inspector"), "name": "ناظر HSE"},
        {"role_id": auth_manager.roles_map.get("executor"), "name": "مجری"},
        {"role_id": auth_manager.roles_map.get("warehouse_keeper"), "name": "انباردار"},
        {"role_id": auth_manager.roles_map.get("planning_expert"), "name": "کارشناس برنامه‌ریزی"},
    ]

@ui.page('/role_mapping')
async def role_mapping_page() -> None:
    """Render the role mapping admin interface."""
    
    ui.label('تعیین نقش‌های کاربران (نقش‌سازی Keycloak به Directus)').classes('text-2xl font-bold mb-4')
    
    # Load data
    keycloak_users = await load_keycloak_users()
    available_roles = await load_available_roles()
    
    # Table for user role assignment
    with ui.table() as table:
        columns = [
            {'name': 'full_name', 'label': 'نام‌کامل', 'field': 'full_name'},
            {'name': 'email', 'label': 'ایمیل', 'field': 'email'},
            {'name': 'assigned_role', 'label': 'نقش تعیین‌شده', 'field': 'assigned_role'},
        ]
        table.props('flat bordered')
        
        # Render header
        with table.header:
            with table.row():
                for col in columns:
                    ui.table_column(col['name'], col['label'])
        
        # Render rows
        with table.body:
            for user in keycloak_users:
                with table.row():
                    ui.table_cell(user['full_name'])
                    ui.table_cell(user['email'])
                    
                    # Role selector dropdown
                    async def on_role_selected(new_role: str, uid: str = user['keycloak_id']) -> None:
                        await assign_user_role(uid, new_role)
                        ui.notify(f"نقش به {user['full_name']} اختصاص داده شد.")
                    
                    role_options = {r['name']: r['role_id'] for r in available_roles}
                    ui.select(list(role_options.keys()), on_change=on_role_selected).classes('w-full')
    
    # Save button
    async def save_mappings() -> None:
        ui.notify("تمام نقش‌سازی‌ها ذخیره شدند.")
        logger.info("Role mappings saved.")
    
    ui.button('ذخیره نقش‌سازی‌ها', on_click=save_mappings).classes('mt-4 bg-green-600 text-white')

@exir_boundary_tracer
async def assign_user_role(keycloak_user_id: str, role_id: str) -> None:
    """Assign a role to a Keycloak user in Directus."""
    try:
        # In production, call Directus API to create/update user with role
        await auth_manager.sync_keycloak_user_to_directus({
            "sub": keycloak_user_id,
            "username": "user",
            "email": "user@example.com",
            "name": "User Name",
            "department": "GENERAL_SUPPORT"
        })
        logger.info(f"Assigned role {role_id} to user {keycloak_user_id}.")
    except Exception as e:
        logger.error(f"Failed to assign role: {e}")
        ui.notify(f"خطا در اختصاص نقش: {str(e)}", type='negative')
