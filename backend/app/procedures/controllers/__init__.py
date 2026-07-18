"""Procedure-quiz controllers."""

from app.procedures.controllers.procedure_controller import (
    guard_router as procedures_guard_router,
)
from app.procedures.controllers.procedure_controller import router as procedures_router

__all__ = ["procedures_router", "procedures_guard_router"]
