"""
ScheduleExportService — the schedule *read model* (part B, task 10·01).

Three downstream products need exactly the same answer — *who is placed on what,
and when*: the schedule grid Excel (02), the per-guard "positions" Excel (03) and
the personal Telegram message (04). Rather than let each re-query and re-interpret
the raw assignments, this service resolves that answer **once** into a
:class:`WeekSchedule` with two cuts of the same data:

- ``by_position`` — board rows in board order (from ``board_service``); for each
  position, 7 days, each day carrying its (possibly tiled) list of placements.
- ``by_guard`` — every active guard with their own list of shifts (day → position
  → hours), sorted by ``(day_index, start)``.

Both cuts are produced **after contiguous-shift merging** (see
``_merge_contiguous``): a guard sitting two back-to-back segments on the *same*
position/day (07:00–15:00 + 15:00–19:00) reads as one 07:00–19:00 shift. The merge
lives here, once, so all three products agree.

Hours per placement (``_resolve_hours``): the assignment's ``segment_start`` /
``segment_end`` when set, otherwise the position's window for that day (already
resolved by the board). ``end <= start`` means the shift crosses midnight; it is
kept as-is and the formatters (02/04) render "→ next day" as needed.
"""

import logging
import uuid
from dataclasses import dataclass, field

from app.models.schedule_week import ScheduleWeek
from app.repositories.user_repository import UserRepository
from app.schedule_builder.services.assignment_service import AssignmentService
from app.schedule_builder.services.board_service import BoardService
from app.schedule_builder.utils import intervals as iv

logger = logging.getLogger("ilutzim")


# ── Read-model dataclasses (internal — never serialised to the API) ──────────


@dataclass
class Placement:
    """One guard on a cell, with the hours actually worked."""

    user_id: uuid.UUID
    user_name: str
    start: str
    end: str


@dataclass
class PositionDay:
    """One day-column of a position row: its window and who fills it."""

    day_index: int
    date: str
    active: bool
    placements: list[Placement] = field(default_factory=list)
    # Uncovered sub-windows of a *staffed* cell (partial coverage), as
    # ``(start, end)`` HH:MM pairs. Empty when the cell is fully covered — or
    # fully empty (a wholly-unstaffed cell is flagged elsewhere, not split).
    gaps: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class PositionRow:
    """A board row (position) with its 7 day-columns, in board order."""

    position_id: uuid.UUID
    name: str
    band: str
    days: list[PositionDay]
    # The position's *regular* hours (most-common daily window). Lets consumers
    # print a placement's hours only when they deviate from the norm.
    canonical_window: dict | None = None
    # Event / non-splitting position (guards share the whole window). Drives the
    # distinct Excel colour and the absence of a coverage requirement.
    is_event: bool = False
    # Event-only fixed participant count — the Excel tiles the cell into this many
    # slots and paints the missing ones amber. None = unlimited (no fixed slots).
    event_required_count: int | None = None


@dataclass
class GuardShift:
    """One shift of a single guard: day → position → hours."""

    day_index: int
    date: str
    position_id: uuid.UUID
    position_name: str
    start: str
    end: str
    # Event / non-splitting shift — rendered as a dedicated 📣 Telegram sentence.
    is_event: bool = False


@dataclass
class GuardSchedule:
    """Every shift a single active guard works this week (may be empty)."""

    user_id: uuid.UUID
    user_name: str
    telegram_id: str | None
    # Carried for the publish-*preview* only (identity check on non-real data);
    # the real broadcast routes by ``telegram_id`` and never reads this.
    phone_number: str = ""
    shifts: list[GuardShift] = field(default_factory=list)


@dataclass
class WeekSchedule:
    """The resolved schedule for one week, in two cuts of the same data."""

    week: ScheduleWeek
    days: list[dict]  # [{"index": int, "date": str}]
    by_position: list[PositionRow]
    by_guard: list[GuardSchedule]
    # Per-day header labels from the week's effective profile (e.g. {"1": "חג"}),
    # string day-index keyed. Carried so the schedule grid (Excel + PNG) can print
    # them under each day name. Empty on the actual-schedule cut (no profile meta).
    day_labels: dict = field(default_factory=dict)


# ── Pure helpers ─────────────────────────────────────────────────────────────


def _resolve_hours(segment_start, segment_end, window) -> tuple[str, str] | None:
    """Hours for a placement: its own segment if set, else the day's window.

    Returns ``(start, end)`` or ``None`` when neither is available (an assignment
    on an inactive day — structurally unexpected; the caller logs and skips).
    """
    if segment_start and segment_end:
        return segment_start, segment_end
    if window:
        return window["start"], window["end"]
    return None


def _merge_contiguous(shifts: list[dict], key, combine=None) -> list[dict]:
    """Merge back-to-back runs of the same guard/position within one day.

    ``shifts`` are dicts carrying at least ``start`` / ``end`` (``HH:MM``). Items
    are grouped by ``key(shift)``; inside a group, ordered by ``start``, a run
    whose ``prev.end == next.start`` collapses into one span (chaining 07–15,
    15–19, 19–23 → 07–23). Distinct keys never merge (tiling between guards, or
    two different positions, stays split). The input group order is preserved.

    ``combine(acc, cur)`` — when set — is called each time ``cur`` folds into the
    open span ``acc`` (after its ``end`` has been widened), returning the merged
    dict. Use it to reconcile metadata that differs across the run (e.g. joining
    two position names). Without it, the span keeps the first item's fields.

    Overlap (``next.start < prev.end``) is not expected — a guard is not placed on
    two overlapping segments — but if it happens we widen to the far edge and warn
    rather than crash.
    """
    groups: dict = {}
    order: list = []
    for s in shifts:
        k = key(s)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(s)

    # All ordering/merging happens on the 07:00 anchor axis (minutes-from-07:00),
    # never on wall-clock HH:MM strings: a night tail like 01:00 is *late* on the
    # security day, so a lexicographic sort/compare would flip 01:00–07:00 ahead of
    # 07:00–15:00 (B-2). A shift ending at 07:00 is minute 0 by ``to_min`` but marks
    # the *end* of the day, so treat that edge as 1440 for end comparisons only
    # (mirrors ``end_min ... or 1440`` in the form validator).
    def _end_min(s: dict) -> int:
        return iv.to_min(s["end"]) or iv.DAY_MINUTES

    merged: list[dict] = []
    for k in order:
        run: list[dict] = []
        for cur in sorted(groups[k], key=lambda s: iv.to_min(s["start"])):
            if run and iv.to_min(cur["start"]) == _end_min(run[-1]):
                run[-1] = {**run[-1], "end": cur["end"]}
                if combine:
                    run[-1] = combine(run[-1], cur)
            elif run and iv.to_min(cur["start"]) < _end_min(run[-1]):
                logger.warning(
                    "overlapping segments merged for key %s: %s / %s",
                    k, run[-1], cur,
                )
                far = cur if _end_min(cur) > _end_min(run[-1]) else run[-1]
                run[-1] = {**run[-1], "end": far["end"]}
                if combine:
                    run[-1] = combine(run[-1], cur)
            else:
                run.append(dict(cur))

        # Circular wrap-join: the 07:00 anchor is the day boundary, so a night
        # tail ending at 07:00 and a morning span starting at 07:00 are one
        # continuous presence for the guard (01:00–07:00 + 07:00–15:00 →
        # 01:00–15:00), even though on the linear axis they sit at opposite ends.
        # After the anchor sort the 07:00-*starting* span is run[0] and the
        # 07:00-*ending* tail is run[-1]; fold the tail into the head so the
        # personal message reads one block, not two reversed ones (B-2).
        if (
            len(run) >= 2
            and iv.to_min(run[0]["start"]) == 0
            and iv.to_min(run[-1]["end"]) == 0
        ):
            head = {**run[0], "start": run[-1]["start"]}
            if combine:
                head = combine(head, run[-1])
            run = [head, *run[1:-1]]
        merged.extend(run)
    return merged


def order_unverified_first(guards: list) -> list:
    """Stable reorder putting guards with no linked Telegram first.

    Guards who never linked Telegram (``telegram_id is None``) can't receive
    their schedule over the bot — the admin has to hand it to them off-band. The
    per-guard "positions" Excel and the publish-preview both float these guards to
    the top so the admin sees them first. ``sorted`` is stable, so the repo's
    name order is preserved within each group (unlinked first, then linked).
    """
    return sorted(guards, key=lambda g: g.telegram_id is not None)


def _join_positions(acc: dict, cur: dict) -> dict:
    """Combine the position names of a merged cross-position run.

    Names accumulate unique and in chronological order, joined by ``" / "`` — so
    07–15 ``אחראי משמרת`` + 15–19 ``אחראי משמרת (ערב)`` reads as
    ``אחראי משמרת / אחראי משמרת (ערב)``. A repeated name (e.g. A → B → A) is not
    duplicated. The span keeps the first placement's ``position_id`` for identity.
    """
    names = acc["position_name"].split(" / ")
    if cur["position_name"] not in names:
        names.append(cur["position_name"])
    return {**acc, "position_name": " / ".join(names)}


# ── Source-agnostic core ─────────────────────────────────────────────────────
#
# Everything below builds a WeekSchedule from *already-loaded* inputs and knows
# nothing about where they came from. Two producers feed it: the planned read
# model (ScheduleExportService — board + schedule_assignments) and the actual
# read model (ActualScheduleExportService — the week's editable execution copy).
# Sharing the core is what guarantees a freshly-seeded actual schedule reads
# EXACTLY like the plan (the step-03 parity test pins this).
#
# Expected shapes:
# - ``rows``        — board-row dicts (``board_service.build_position_row``).
# - ``assignments`` — objects exposing ``position_id`` / ``day_index`` /
#   ``user_id`` / ``segment_start`` / ``segment_end`` / ``user.full_name``
#   (ScheduleAssignment natively; ActualAssignment via its alias property).
# - ``guards``      — active users, already name-sorted by the repo.


def build_week_schedule(
    week, days, rows, assignments, guards, day_labels=None
) -> WeekSchedule:
    """Assemble both cuts (``by_position`` + ``by_guard``) from loaded inputs.

    ``day_labels`` (optional) is the effective profile's per-day header-label map;
    the planned cut passes it through so the grid can annotate day columns, the
    actual cut omits it (it has no profile meta).
    """
    date_by_day = {d["index"]: d["date"] for d in days}

    # Index assignments by cell; each carries .user eager-loaded.
    by_cell: dict[tuple, list] = {}
    for a in assignments:
        by_cell.setdefault((a.position_id, a.day_index), []).append(a)

    return WeekSchedule(
        week=week,
        days=[{"index": d["index"], "date": d["date"]} for d in days],
        by_position=_build_by_position(rows, by_cell),
        by_guard=_build_by_guard(rows, assignments, guards, date_by_day),
        day_labels=dict(day_labels or {}),
    )


def _build_by_position(rows, by_cell) -> list[PositionRow]:
    """The board-ordered cut: each row's 7 days with their placements."""
    out: list[PositionRow] = []
    for row in rows:
        day_cols: list[PositionDay] = []
        for cell in row["cells"]:
            window = cell["window"]
            raw: list[dict] = []
            for a in by_cell.get((row["position_id"], cell["day_index"]), []):
                hours = _resolve_hours(a.segment_start, a.segment_end, window)
                if hours is None:
                    logger.warning(
                        "assignment %s on inactive cell (pos %s day %s) skipped",
                        a.id, row["position_id"], cell["day_index"],
                    )
                    continue
                raw.append({
                    "user_id": a.user_id,
                    "user_name": a.user.full_name,
                    "start": hours[0],
                    "end": hours[1],
                })
            # Merge a guard's back-to-back segments in this cell; tiling
            # between distinct guards stays split. Order by start for display.
            merged = _merge_contiguous(raw, key=lambda s: s["user_id"])
            merged.sort(key=lambda s: s["start"])
            # Uncovered parts of a *staffed* window (partial coverage): the
            # day's window minus the union of assigned segments. A fully
            # empty cell (no placements) yields no gaps — it is flagged whole,
            # not split into a "gap".
            gaps: list[tuple[str, str]] = []
            if merged and window:
                covered: list[tuple[int, int]] = []
                for s in merged:
                    covered += iv.normalize(s["start"], s["end"])
                win_iv = iv.normalize(window["start"], window["end"])
                gaps = [
                    (iv.to_hhmm(a), iv.to_hhmm(b))
                    for a, b in iv.subtract(win_iv, covered)
                ]
            day_cols.append(PositionDay(
                day_index=cell["day_index"],
                date="",  # position cut is day-indexed; date lives on days[]
                active=cell["active"],
                placements=[
                    Placement(
                        user_id=s["user_id"],
                        user_name=s["user_name"],
                        start=s["start"],
                        end=s["end"],
                    )
                    for s in merged
                ],
                gaps=gaps,
            ))
        out.append(PositionRow(
            position_id=row["position_id"],
            name=row["name"],
            band=row["band"],
            days=day_cols,
            canonical_window=row.get("canonical_window"),
            is_event=row.get("is_event", False),
            event_required_count=row.get("event_required_count"),
        ))
    return out


def _build_by_guard(rows, assignments, guards, date_by_day) -> list[GuardSchedule]:
    """The per-guard cut: every active guard with their sorted shifts."""
    # position_id → (name, {day_index: window}) from the board.
    pos_info: dict = {}
    for row in rows:
        windows = {c["day_index"]: c["window"] for c in row["cells"]}
        pos_info[row["position_id"]] = (
            row["name"], windows, row.get("is_event", False)
        )

    raw_by_user: dict = {}
    for a in assignments:
        info = pos_info.get(a.position_id)
        if info is None:
            logger.warning(
                "assignment %s references position %s not on the board — skipped",
                a.id, a.position_id,
            )
            continue
        position_name, windows, is_event = info
        hours = _resolve_hours(
            a.segment_start, a.segment_end, windows.get(a.day_index)
        )
        if hours is None:
            logger.warning(
                "assignment %s on inactive cell (pos %s day %s) skipped",
                a.id, a.position_id, a.day_index,
            )
            continue
        raw_by_user.setdefault(a.user_id, []).append({
            "day_index": a.day_index,
            "position_id": a.position_id,
            "position_name": position_name,
            "start": hours[0],
            "end": hours[1],
            "is_event": is_event,
        })

    out: list[GuardSchedule] = []
    for guard in guards:  # already sorted by name by the repo
        raw = raw_by_user.get(guard.id, [])
        # Merge back-to-back segments within a day *across positions*: a guard
        # working 07–15 then 15–19 on a different position reads as one 07–19
        # span, its position names joined (``A / B``). Different days stay
        # separate. Then order the guard's week chronologically.
        # Include is_event in the merge key so an event shift never folds into
        # a neighbouring normal shift (they render very differently downstream).
        merged = _merge_contiguous(
            raw,
            key=lambda s: (s["day_index"], s["is_event"]),
            combine=_join_positions,
        )
        merged.sort(key=lambda s: (s["day_index"], s["start"]))
        out.append(GuardSchedule(
            user_id=guard.id,
            user_name=guard.full_name,
            telegram_id=guard.telegram_id,
            phone_number=guard.phone_number,
            shifts=[
                GuardShift(
                    day_index=s["day_index"],
                    date=date_by_day.get(s["day_index"], ""),
                    position_id=s["position_id"],
                    position_name=s["position_name"],
                    start=s["start"],
                    end=s["end"],
                    is_event=s["is_event"],
                )
                for s in merged
            ],
        ))
    return out


class ScheduleExportService:
    """Resolve a week's built schedule into the shared read model."""

    def __init__(
        self,
        board_service: BoardService,
        assignment_service: AssignmentService,
        user_repo: UserRepository,
    ) -> None:
        self._board = board_service
        self._assignments = assignment_service
        self._user_repo = user_repo

    async def get_week_schedule(self, week_id: uuid.UUID) -> WeekSchedule:
        """Build both cuts (``by_position`` + ``by_guard``) for a week.

        Raises ``WeekNotFoundException`` (via ``resolve_board``) for unknown weeks.
        """
        board = await self._board.resolve_board(week_id)
        assignments = await self._assignments.list_for_week(week_id)
        guards = await self._user_repo.get_active_users()
        return build_week_schedule(
            board["week"], board["days"], board["rows"], assignments, guards,
            day_labels=getattr(board["profile"], "day_labels", None),
        )

    async def send_personal_schedules(
        self, week_id: uuid.UUID, schedule_png: bytes | None = None
    ) -> dict:
        """Broadcast each guard their personal schedule over Telegram.

        When ``schedule_png`` is given (the general schedule-grid image), each guard
        who receives their personal message *also* gets the full schedule as a
        photo — it previews inline and opens with one tap, unlike the old ``.xlsx``.
        Best-effort, so a failed photo delivery never affects the ``sent``/
        ``skipped`` tally, which tracks the personal message only.

        Returns ``{"sent", "skipped", "failed", "total"}``. A guard without a
        ``telegram_id`` is *skipped* (not a failure); a guard who HAS a telegram_id
        but whose delivery errors/returns False is counted as *failed* — surfaced
        separately so a real broadcast failure is not silently indistinguishable
        from "no telegram". A single delivery error is caught and logged so it never
        aborts the whole broadcast. ``sent + skipped + failed == total``.
        """
        # Imported lazily to keep the service import-light and avoid any bot
        # import cost on paths that never broadcast.
        from app.bot.notifications import (
            format_personal_schedule,
            notify_personal_schedule,
            send_photo,
        )

        schedule = await self.get_week_schedule(week_id)
        week = schedule.week
        png_filename = f"סידור_{week.start_date}.png"
        png_caption = f"סידור המשמרות הכללי — {week.start_date} עד {week.end_date}"
        sent = 0
        skipped = 0
        failed = 0
        for guard in schedule.by_guard:
            if not guard.telegram_id:
                skipped += 1
                continue
            text = format_personal_schedule(
                guard, week.start_date, week.end_date
            )
            try:
                delivered = await notify_personal_schedule(guard.telegram_id, text)
            except Exception as exc:  # never let one guard abort the broadcast
                logger.error(
                    "send_personal_schedules: delivery raised for guard %s — %s",
                    guard.user_id, exc,
                )
                delivered = False
            if delivered:
                sent += 1
                # Attach the general schedule image on top of the personal
                # message. Best-effort: a failure here is logged inside
                # send_photo and does not change the sent/skipped tally.
                if schedule_png is not None:
                    try:
                        await send_photo(
                            guard.telegram_id,
                            schedule_png,
                            png_filename,
                            caption=png_caption,
                        )
                    except Exception as exc:
                        logger.error(
                            "send_personal_schedules: schedule PNG delivery "
                            "raised for guard %s — %s",
                            guard.user_id, exc,
                        )
            else:
                # Had a telegram_id but delivery failed — a real failure, not a skip.
                failed += 1
        total = len(schedule.by_guard)
        log = logger.warning if failed else logger.info
        log(
            "send_personal_schedules week %s: sent=%d skipped=%d failed=%d total=%d",
            week_id, sent, skipped, failed, total,
        )
        return {"sent": sent, "skipped": skipped, "failed": failed, "total": total}

    async def preview_personal_schedules(self, week_id: uuid.UUID) -> list[dict]:
        """Dry run of :meth:`send_personal_schedules` — build each guard's message
        but *return* it instead of delivering. Powers the publish-preview page so
        the admin can verify content and recipients (useful while phone numbers /
        telegram ids are still placeholder data). Sends nothing.

        Each item: ``{user_name, phone_number, telegram_id, would_send, message}``.
        ``would_send`` is ``False`` for a guard with no ``telegram_id`` — exactly
        the ones the real broadcast skips.
        """
        from app.bot.notifications import format_personal_schedule

        schedule = await self.get_week_schedule(week_id)
        week = schedule.week
        return [
            {
                "user_name": guard.user_name,
                "phone_number": guard.phone_number,
                "telegram_id": guard.telegram_id,
                "would_send": bool(guard.telegram_id),
                "message": format_personal_schedule(
                    guard, week.start_date, week.end_date
                ),
            }
            for guard in order_unverified_first(schedule.by_guard)
        ]

