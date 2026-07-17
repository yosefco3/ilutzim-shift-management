"""
Procedure broadcast — the synchronous publish fan-out.

The publish endpoint runs this **synchronously** (exactly like
``WeekService.publish_week``): guard count is in the tens, so the request
completes in seconds and the admin gets true ``{sent, skipped, total}`` counts.
A fire-and-forget task could be GC'd mid-flight and would stamp PUBLISHED with
zero deliveries — unacceptable.

``ProcedurePublisher`` is the seam: the real implementation uses the chunked
``send_procedure`` Telegram helper; tests inject a fake to assert counts
without the bot.
"""

import logging
from typing import Protocol, runtime_checkable

from app.procedures.models.procedure import Procedure

logger = logging.getLogger("ilutzim")


@runtime_checkable
class ProcedurePublisher(Protocol):
    """Fan a published procedure out to a list of guards."""

    async def broadcast(
        self,
        recipients: list[str],
        title: str,
        body_text: str,
        procedure_id,
    ) -> dict:
        """Send the procedure to each recipient.

        Returns ``{"sent": int, "skipped": int, "total": int}``. A blocked bot
        (guard stopped the bot) logs and counts as skipped, never raises.
        """
        ...


class RealProcedurePublisher:
    """Publishes a procedure via the chunked Telegram ``send_procedure`` helper.

    The start-quiz inline keyboard is attached to the procedure's last chunk by
    ``send_procedure`` itself; here we only build that keyboard once and fan out.
    """

    def __init__(self, keyboard_factory=None) -> None:
        # keyboard_factory(procedure_id) -> InlineKeyboardMarkup | None.
        # Defaults to the procedures start-quiz keyboard. Injected so this
        # module stays decoupled from the bot keyboard module at import time
        # (and so tests can pass a stub).
        self._keyboard_factory = keyboard_factory

    async def broadcast(
        self,
        recipients: list[str],
        title: str,
        body_text: str,
        procedure_id,
    ) -> dict:
        from app.bot.notifications import send_procedure

        keyboard = None
        if self._keyboard_factory is not None:
            try:
                keyboard = self._keyboard_factory(procedure_id)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Procedure keyboard build failed: %s", exc)
                keyboard = None

        sent = 0
        skipped = 0
        for tg_id in recipients:
            ok = await send_procedure(
                tg_id, title, body_text, reply_markup=keyboard
            )
            if ok:
                sent += 1
            else:
                skipped += 1
        total = len(recipients)
        if skipped:
            logger.warning(
                "procedure publish %s: %d of %d sends skipped",
                procedure_id, skipped, total,
            )
        return {"sent": sent, "skipped": skipped, "total": total}
