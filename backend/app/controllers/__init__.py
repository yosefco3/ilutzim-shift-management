"""
Controllers package — FastAPI routers.
"""

from app.controllers.auth_controller import router as auth_router
from app.controllers.submission_controller import router as submission_router
from app.controllers.admin_users_controller import router as admin_users_router
from app.controllers.admin_weeks_controller import router as admin_weeks_router
from app.controllers.admin_notifications_controller import router as admin_notifications_router
from app.controllers.admin_export_controller import router as admin_export_router
from app.controllers.admin_settings_controller import router as admin_settings_router
from app.controllers.constraints_import_controller import router as constraints_import_router

__all__ = [
    "auth_router",
    "submission_router",
    "admin_users_router",
    "admin_weeks_router",
    "admin_notifications_router",
    "admin_export_router",
    "admin_settings_router",
    "constraints_import_router",
]