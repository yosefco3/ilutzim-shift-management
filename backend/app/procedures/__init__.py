"""Procedure-quiz feature module (סד"פ).

Mirrors the structure of ``app/attendance``: models / repositories / services /
controllers + ``dependencies.py``. Registered in ``main.py`` and the bot router
only when ``PROCEDURES_ENABLED`` is on, so with the flag off every path here is
dormant (endpoints return 404, no bot handlers, no scheduler job).
"""
