"""
Part B — Schedule Builder (בונה הסידור).

This package is the **code boundary** for part B of the application. The app has
two parts:

  • Part A — availability collection (existing): Telegram + Excel → the
    ``WeeklySubmission`` / ``DailyStatus`` / ``ShiftWindow`` model. Lives under
    ``app/{models,repositories,services,controllers,schemas}/``.

  • Part B — schedule builder (this package): activation profiles → positions →
    assignment board → export. **All** of part B's code lives here.

Dependency rule (one-directional):
  • Part B MAY import from part A (e.g. the availability model, ``get_pool``,
    ``require_admin_role``) — part B consumes availability.
  • Part A MUST NOT import from ``app.schedule_builder`` — the only exception is
    a single, explicitly-commented import in ``app/models/__init__.py`` so
    Alembic autogenerate sees part-B models in ``Base.metadata``.

Part-B models inherit from ``app.models.base.BaseModel`` (same ``Base.metadata``,
same database) but physically live under this package.
"""
