"""
ActualScheduleService — seeding the actual-schedule copy (step 02).

``ensure_for_week`` is the single birth-point of a week's actual schedule:

- Called from the Sunday rollover (``WeekService.lock_expired_open_weeks``) the
  moment a week starts — the planned board freezes and its editable execution
  copy is born (``source="rollover"``).
- Called lazily from every read path (the actual read model, the actual board
  API) — covering weeks that predate the feature and rollovers missed while the
  server was down (``source="lazy"``).

It is strictly **idempotent**: once a copy exists it is returned untouched, so
admin edits are never overwritten no matter how many times it runs.

Seeding copies the *live* planned data — the effective profile's positions plus
the week's ``schedule_assignments`` — which is exact for a week that just
started. For an old week whose profile changed since, it is a declared
best-effort approximation (the comparison ran against the same live data until
now anyway).
"""

import logging
import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from app.exceptions import (
    AppBaseException,
    AssignmentNotFoundException,
    CellInactiveException,
    GuardAlreadyAssignedException,
    PositionNotFoundException,
    WeekNotFoundException,
)
from app.repositories.schedule_week_repository import ScheduleWeekRepository
from app.schedule_builder.models.actual_assignment import ActualAssignment
from app.schedule_builder.models.actual_position import ActualPosition
from app.schedule_builder.models.actual_schedule import ActualSchedule
from app.schedule_builder.repositories.actual_schedule_repository import (
    ActualScheduleRepository,
)
from app.schedule_builder.repositories.assignment_repository import (
    AssignmentRepository,
)
from app.schedule_builder.repositories.position_repository import PositionRepository
from app.schedule_builder.services.week_profile_service import WeekProfileService
from app.utils.date_utils import today_il

logger = logging.getLogger("ilutzim")


class ActualScheduleNotAvailableException(AppBaseException):
    """The week has not started yet — its actual schedule does not exist.

    A future week is edited on the *planning* board; the actual layer only
    exists from the moment the week starts.
    """

    status_code = 409
    message = "השבוע טרם התחיל — סידור בפועל נוצר רק משבוע שהתחיל"


class ActualScheduleService:
    """Seeds (and later edits) the week's actual-schedule copy."""

    def __init__(
        self,
        actual_repo: ActualScheduleRepository,
        week_repo: ScheduleWeekRepository,
        week_profile_service: WeekProfileService,
        position_repo: PositionRepository,
        assignment_repo: AssignmentRepository,
        profile_repo=None,  # ProfileRepository — needed only for save_as_profile
    ) -> None:
        self._repo = actual_repo
        self._week_repo = week_repo
        self._wp_service = week_profile_service
        self._position_repo = position_repo
        self._assignment_repo = assignment_repo
        self._profile_repo = profile_repo

    async def ensure_for_week(
        self, week_id: uuid.UUID, *, source: str = "lazy"
    ) -> ActualSchedule:
        """Return the week's actual schedule, seeding it 1:1 if missing.

        Idempotent — an existing copy is returned as-is (edits survive).
        Raises :class:`WeekNotFoundException` for an unknown week and
        :class:`ActualScheduleNotAvailableException` for a week that has not
        started yet.
        """
        existing = await self._repo.get_by_week(week_id)
        if existing is not None:
            return existing

        week = await self._week_repo.get_by_id(week_id)
        if week is None:
            raise WeekNotFoundException()
        if week.start_date > today_il():
            raise ActualScheduleNotAvailableException()

        return await self._seed(week, source)

    async def _seed(self, week, source: str) -> ActualSchedule:
        """Copy the planned board (positions + assignments) into a new copy."""
        actual = ActualSchedule(week_id=week.id, seed_source=source)
        self._repo.session.add(actual)
        await self._repo.session.flush()

        # 1. Positions — the effective profile's rows, copied field-for-field.
        #    A week with no resolvable profile seeds an EMPTY (valid) copy.
        source_to_actual: dict[uuid.UUID, uuid.UUID] = {}
        try:
            profile, _ = await self._wp_service.get_effective_profile(week.id)
            planned_positions = await self._position_repo.get_by_profile(profile.id)
        except Exception as exc:  # ProfileNotFoundException and friends
            logger.warning(
                "actual seed: week %s has no resolvable profile (%s) — seeding empty",
                week.id, exc,
            )
            planned_positions = []

        for planned in planned_positions:
            copy = ActualPosition(
                actual_schedule_id=actual.id,
                name=planned.name,
                day_schedules=dict(planned.day_schedules or {}),
                required_attributes=list(planned.required_attributes or []),
                display_order=planned.display_order,
                is_event=planned.is_event,
                event_required_count=planned.event_required_count,
                source_position_id=planned.id,
            )
            self._repo.session.add(copy)
            await self._repo.session.flush()
            source_to_actual[planned.id] = copy.id

        # 2. Assignments — mapped onto the copied positions. An assignment
        #    pointing at a position no longer in the profile (possible on an
        #    old week) is skipped with a warning, not fatal.
        planned_assignments = await self._assignment_repo.list_for_week(week.id)
        skipped = 0
        for planned in planned_assignments:
            actual_position_id = source_to_actual.get(planned.position_id)
            if actual_position_id is None:
                skipped += 1
                continue
            self._repo.session.add(
                ActualAssignment(
                    actual_schedule_id=actual.id,
                    actual_position_id=actual_position_id,
                    day_index=planned.day_index,
                    user_id=planned.user_id,
                    segment_start=planned.segment_start,
                    segment_end=planned.segment_end,
                )
            )
        if skipped:
            logger.warning(
                "actual seed: week %s — %d assignment(s) skipped "
                "(their planned position is gone from the profile)",
                week.id, skipped,
            )

        await self._repo.session.commit()
        logger.info(
            "actual seed: week %s seeded (%s) — %d positions, %d assignments",
            week.id, source, len(source_to_actual),
            len(planned_assignments) - skipped,
        )
        return await self._repo.get_by_week(week.id)

    # ── The actual board (read) ──────────────────────────────────────────────

    async def get_board(self, week_id: uuid.UUID) -> dict:
        """The full actual board: rows, assignments and soft warnings.

        Seeds lazily on first read (any started week, however old).
        """
        from app.schedule_builder.services.actual_warnings import (
            compute_actual_warnings,
        )
        from app.schedule_builder.services.board_service import (
            build_position_row,
            sort_rows_by_band,
        )

        actual = await self.ensure_for_week(week_id)
        week = await self._week_repo.get_by_id(week_id)
        positions = await self._repo.list_positions(actual.id)
        assignments = await self._repo.list_assignments(actual.id)
        reinforcements = await self._repo.list_reinforcements(actual.id)

        rows = []
        for position in positions:
            row = build_position_row(position)
            row["source_position_id"] = position.source_position_id
            row["is_adhoc"] = position.source_position_id is None
            rows.append(row)
        sort_rows_by_band(rows)

        days = [
            {"index": i, "date": (week.start_date + timedelta(days=i)).isoformat()}
            for i in range(7)
        ]
        return {
            "week": week,
            "actual_schedule_id": actual.id,
            "seeded_at": actual.seeded_at,
            "seed_source": actual.seed_source,
            "days": days,
            "rows": rows,
            "assignments": assignments,
            "reinforcements": reinforcements,
            "warnings": compute_actual_warnings(rows, assignments),
        }

    # ── Assignment editing (no time gate — reality outranks planning) ───────

    async def _get_owned_position(
        self, actual_position_id: uuid.UUID
    ) -> ActualPosition:
        position = await self._repo.get_position(actual_position_id)
        if position is None:
            raise PositionNotFoundException()
        return position

    async def assign(
        self,
        actual_position_id: uuid.UUID,
        day_index: int,
        user_id: uuid.UUID,
        segment_start: str | None = None,
        segment_end: str | None = None,
        expected_schedule_id: uuid.UUID | None = None,
    ) -> ActualAssignment:
        """Place a guard on an actual cell. Free editing: no availability
        check, no two-guard cap, inactive guards allowed (retro reality).
        Only structural rules apply: the position must exist (and belong to
        ``expected_schedule_id`` when given — the week in the URL) and be
        active that day, and the same guard can't sit twice in one cell.
        """
        position = await self._get_owned_position(actual_position_id)
        if (
            expected_schedule_id is not None
            and position.actual_schedule_id != expected_schedule_id
        ):
            raise PositionNotFoundException()
        if str(day_index) not in (position.day_schedules or {}):
            raise CellInactiveException()

        assignment = ActualAssignment(
            actual_schedule_id=position.actual_schedule_id,
            actual_position_id=actual_position_id,
            day_index=day_index,
            user_id=user_id,
            segment_start=segment_start,
            segment_end=segment_end,
        )
        self._repo.session.add(assignment)
        try:
            await self._repo.session.commit()
        except IntegrityError:
            await self._repo.session.rollback()
            raise GuardAlreadyAssignedException()
        await self._repo.session.refresh(assignment, ["user"])
        return assignment

    async def unassign(self, actual_assignment_id: uuid.UUID) -> None:
        assignment = await self._repo.get_assignment(actual_assignment_id)
        if assignment is None:
            raise AssignmentNotFoundException()
        await self._repo.session.delete(assignment)
        await self._repo.session.commit()

    async def update_segment(
        self,
        actual_assignment_id: uuid.UUID,
        segment_start: str | None,
        segment_end: str | None,
    ) -> ActualAssignment:
        """Set/clear an assignment's time segment (null/null = whole window)."""
        assignment = await self._repo.get_assignment(actual_assignment_id)
        if assignment is None:
            raise AssignmentNotFoundException()
        assignment.segment_start = segment_start
        assignment.segment_end = segment_end
        await self._repo.session.commit()
        await self._repo.session.refresh(assignment, ["user"])
        return assignment

    # ── Position editing (the "unforeseen event" story) ─────────────────────

    async def add_position(
        self,
        week_id: uuid.UUID,
        *,
        name: str,
        day_schedules: dict,
        required_attributes: list | None = None,
        is_event: bool = False,
        event_required_count: int | None = None,
    ) -> ActualPosition:
        """Add an ad-hoc position mid-week (``source_position_id`` stays None).

        Free-form — not tied to any profile; appended after the existing rows.
        """
        actual = await self.ensure_for_week(week_id)
        positions = await self._repo.list_positions(actual.id)
        position = ActualPosition(
            actual_schedule_id=actual.id,
            name=name,
            day_schedules=dict(day_schedules or {}),
            required_attributes=list(required_attributes or []),
            display_order=max((p.display_order for p in positions), default=0) + 1,
            is_event=is_event,
            event_required_count=event_required_count if is_event else None,
            source_position_id=None,
        )
        self._repo.session.add(position)
        await self._repo.session.commit()
        return position

    async def update_position(
        self,
        actual_position_id: uuid.UUID,
        *,
        name: str | None = None,
        day_schedules: dict | None = None,
        required_attributes: list | None = None,
        is_event: bool | None = None,
        event_required_count: int | None = None,
    ) -> ActualPosition:
        """Edit an actual position (hours, active days, name, event-ness).

        Narrowing a window / dropping a day deliberately does NOT delete
        assignments that no longer fit — they surface as the
        ``assignments_outside_window`` soft warning and the admin decides.
        """
        position = await self._get_owned_position(actual_position_id)
        if name is not None:
            position.name = name
        if day_schedules is not None:
            position.day_schedules = dict(day_schedules)
        if required_attributes is not None:
            position.required_attributes = list(required_attributes)
        if is_event is not None:
            position.is_event = is_event
        if event_required_count is not None:
            position.event_required_count = event_required_count
        if not position.is_event:
            position.event_required_count = None
        await self._repo.session.commit()
        return position

    async def remove_position(self, actual_position_id: uuid.UUID) -> None:
        """Drop a position from the actual board (its assignments cascade).

        This is exactly the "position cancelled mid-week" story — the row
        simply stops existing for the comparison and the reports.
        """
        position = await self._get_owned_position(actual_position_id)
        await self._repo.session.delete(position)
        await self._repo.session.commit()

    # ── Reinforcement guards (מתגברים) ───────────────────────────────────────

    async def add_reinforcement(
        self,
        week_id: uuid.UUID,
        *,
        first_name: str,
        last_name: str,
        phone_number: str | None = None,
        note: str | None = None,
        supervisor_name: str | None = None,
    ):
        """Create a one-off external reinforcement card for this week.

        Creates a flagged ``User`` row (``is_reinforcement=True`` — invisible
        everywhere except this board) + the card that puts them in the week's
        pool. No phone → a unique placeholder (the column is unique+required).
        """
        from app.models.user import User
        from app.schedule_builder.models.actual_reinforcement import (
            ActualReinforcement,
        )

        actual = await self.ensure_for_week(week_id)

        user = User(
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number or f"EXT-{uuid.uuid4().hex[:12]}",
            roles=[],
            is_active=True,
            is_reinforcement=True,
            exemptions_notes=note,
        )
        self._repo.session.add(user)
        try:
            await self._repo.session.flush()
        except IntegrityError:  # duplicate phone number
            await self._repo.session.rollback()
            from app.exceptions import ConflictException

            raise ConflictException("מספר הטלפון כבר קיים במערכת")

        card = ActualReinforcement(
            actual_schedule_id=actual.id,
            user_id=user.id,
            supervisor_name=supervisor_name,
        )
        self._repo.session.add(card)
        await self._repo.session.commit()
        logger.info(
            "actual reinforcement: %s added to week %s (user=%s)",
            user.full_name, week_id, user.id,
        )
        return await self._repo.get_reinforcement(card.id)

    async def remove_reinforcement(self, card_id: uuid.UUID) -> None:
        """Remove a reinforcement card — AND its one-off user row.

        The user's assignments on this week's board cascade away with the user
        (that is the point: the helper never existed as far as the team goes).
        """
        from app.models.user import User

        card = await self._repo.get_reinforcement(card_id)
        if card is None:
            raise AssignmentNotFoundException("כרטיס מתגבר לא נמצא")
        # Load explicitly (session.get gives no eager relationship).
        user = await self._repo.session.get(User, card.user_id)
        await self._repo.session.delete(card)
        if user is not None and user.is_reinforcement:
            await self._repo.session.delete(user)
        await self._repo.session.commit()

    async def export_reinforcements_report(self, start, end) -> bytes:
        """The reinforcements report xlsx for [start, end] (any period cut)."""
        from app.exceptions import ValidationException
        from app.schedule_builder.services.reinforcements_report import (
            collect_report_rows,
            render_reinforcements_report,
        )

        if start is None or end is None or end < start:
            raise ValidationException("טווח תאריכים שגוי")

        assignments = await self._repo.list_reinforcement_assignments_between(
            start, end
        )
        schedule_ids = list({a.actual_schedule_id for a in assignments})
        cards_by_key = {
            (c.user_id, c.actual_schedule_id): c
            for c in await self._repo.list_cards_for_schedules(schedule_ids)
        }
        rows = collect_report_rows(assignments, cards_by_key, start, end)
        return render_reinforcements_report(rows, start, end)

    # ── Promote the copy to a reusable profile ──────────────────────────────

    async def save_as_profile(self, week_id: uuid.UUID, name: str):
        """Create a regular ActivationProfile from this week's actual board.

        The completion of the "profile that starts with all the data" decision:
        the copy stays private per-week, and the admin explicitly promotes a
        week worth keeping. The new profile is a full position-for-position
        clone (ad-hoc rows included, display order preserved), unbound to any
        week — it simply appears in the profiles list for future use.
        """
        from app.exceptions import ConflictException
        from app.schedule_builder.models.activation_profile import ActivationProfile
        from app.schedule_builder.models.position import Position

        if self._profile_repo is None:  # assembly error, not a user error
            raise RuntimeError("save_as_profile requires a ProfileRepository")

        actual = await self.ensure_for_week(week_id)
        existing = await self._profile_repo.get_all_ordered()
        if any(p.name == name for p in existing):
            raise ConflictException("פרופיל בשם זה כבר קיים")

        profile = ActivationProfile(
            name=name,
            is_default=False,
            display_order=await self._profile_repo.max_display_order() + 1,
        )
        self._repo.session.add(profile)
        await self._repo.session.flush()

        for source in await self._repo.list_positions(actual.id):
            self._repo.session.add(Position(
                profile_id=profile.id,
                name=source.name,
                day_schedules=dict(source.day_schedules or {}),
                required_attributes=list(source.required_attributes or []),
                display_order=source.display_order,
                is_event=source.is_event,
                event_required_count=source.event_required_count,
            ))
        await self._repo.session.commit()
        logger.info(
            "actual save-as-profile: week %s promoted to profile %r (id=%s)",
            week_id, name, profile.id,
        )
        return profile
