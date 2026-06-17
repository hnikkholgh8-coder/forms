#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Exir Pooyan NiceGUI Main Application Shell.
Modular UI framework with RTL (right-to-left) support for Persian interface.
"""

import logging
from typing import Dict, Any
from nicegui import ui
from security.audit_logger import exir_boundary_tracer

logger = logging.getLogger("exir_architecture_tracer")

# Configure UI for Persian/RTL
ui.page_title("سیستم مدیریت هوشمند اکسیرپویان")

# Global authentication context
current_user: Dict[str, Any] = {}

@exir_boundary_tracer
async def setup_ui() -> None:
    """Initialize NiceGUI application shell."""
    
    # Title & Header
    with ui.header().classes('w-full bg-blue-600 text-white p-4'):
        ui.label('سیستم مدیریت هوشمند اکسیرپویان (EXIR POOYAN)').classes('text-2xl font-bold')
        ui.label('Smart Work Management System').classes('text-sm italic')

    # Left Sidebar Navigation
    with ui.left_drawer().classes('w-64 bg-gray-100').props('bordered'):
        ui.label('منوی اصلی').classes('text-lg font-bold mb-4')
        
        # Menu items (will be populated dynamically from plugins)
        menu_items = [
            {'label': 'داشبورد', 'route': '/dashboard', 'icon': 'dashboard'},
            {'label': 'کارتابل', 'route': '/cartable', 'icon': 'inbox'},
            {'label': 'صورتجلسات', 'route': '/meetings', 'icon': 'description'},
            {'label': 'ورک‌اوردرها', 'route': '/work_orders', 'icon': 'assignment'},
            {'label': 'تسک‌اوردرها', 'route': '/task_orders', 'icon': 'task'},
            {'label': 'تحویل کارها', 'route': '/handovers', 'icon': 'done_all'},
            {'label': 'تنظیمات سیستمی', 'route': '/settings', 'icon': 'settings'},
        ]
        
        for item in menu_items:
            ui.menu_item(item['label'], lambda route=item['route']: navigate_to(route)).classes('mb-2')

    # Main Content Area
    with ui.column().classes('w-full'):
        # Placeholder content
        ui.label('Welcome to Exir Pooyan').classes('text-xl font-bold mb-4')
        ui.label('Select an option from the menu to begin.').classes('text-gray-600')

    # Footer
    with ui.footer().classes('w-full bg-gray-200 p-4 text-center'):
        ui.label('© 2025 Exir Pooyan Enterprise | All rights reserved.').classes('text-sm')

async def navigate_to(route: str) -> None:
    """Navigate to a specific route."""
    logger.info(f"Navigating to {route}")
    # In production, use ui.navigate(route)

@exir_boundary_tracer
async def initialize_application() -> None:
    """Full application startup sequence."""
    logger.info("Initializing Exir Pooyan NiceGUI Application...")
    
    # Initialize adapters and managers
    from security.auth_manager import auth_manager
    from storage.postgres_adapter import postgres_adapter
    from storage.directus_adapter import directus_adapter
    
    try:
        # Bootstrap authentication system
        await auth_manager.bootstrap_roles()
        logger.info("Authentication system bootstrapped.")
        
        # Initialize database adapters
        await postgres_adapter.initialize()
        await directus_adapter.initialize()
        logger.info("Database adapters initialized.")
        
        # Setup UI
        await setup_ui()
        logger.info("UI setup completed.")
        
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
        raise

@ui.page('/')
async def main_page() -> None:
    """Main landing page."""
    await initialize_application()

if __name__ == '__main__':
    ui.run(host='0.0.0.0', port=8000, title='Exir Pooyan')
