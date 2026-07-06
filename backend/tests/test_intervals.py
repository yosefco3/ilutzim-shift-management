"""
Tests for the security-day interval math (part B — task 06).

The union rule is the crux: overlapping windows merge before measuring.
"""

from app.schedule_builder.utils import intervals as iv


class TestToMin:
    def test_anchor_is_zero(self):
        assert iv.to_min("07:00") == 0

    def test_after_anchor(self):
        assert iv.to_min("16:30") == 570  # 9.5h after 07:00

    def test_before_anchor_wraps(self):
        assert iv.to_min("01:00") == 18 * 60  # 01:00 is 18h after 07:00


class TestNormalize:
    def test_simple(self):
        assert iv.normalize("07:00", "16:30") == [(0, 570)]

    def test_full_day(self):
        assert iv.normalize("07:00", "07:00") == [(0, 1440)]

    def test_night_to_anchor_is_single_piece(self):
        # 23:00 = 960 from 07:00; ends exactly at the anchor → one piece.
        assert iv.normalize("23:00", "07:00") == [(960, 1440)]

    def test_forward_window_no_wrap(self):
        # 19:00=720, 01:00=1080 (both after the 07:00 anchor) → simple interval.
        assert iv.normalize("19:00", "01:00") == [(720, 1080)]

    def test_wrap_past_anchor_splits(self):
        # 05:00=1320, 09:00=120 → crosses the 07:00 anchor, splits in two.
        assert iv.normalize("05:00", "09:00") == [(1320, 1440), (0, 120)]


class TestUnionRule:
    def test_overlapping_windows_union_not_sum(self):
        # 07:00–16:30 (9.5h) ∪ 15:00–19:00 (4h) = 07:00–19:00 = 12h, not 13.5h.
        windows = iv.normalize("07:00", "16:30") + iv.normalize("15:00", "19:00")
        assert iv.duration(windows) == 12 * 60

    def test_disjoint_windows_sum(self):
        windows = iv.normalize("07:00", "09:00") + iv.normalize("12:00", "15:00")
        assert iv.duration(windows) == (2 + 3) * 60

    def test_night_window_duration(self):
        assert iv.duration(iv.normalize("19:00", "07:00")) == 12 * 60

    def test_three_shifts_cover_full_day(self):
        # The real "בובי" data: morning ∪ afternoon ∪ night = 24h.
        windows = (
            iv.normalize("07:00", "16:30")
            + iv.normalize("15:00", "23:00")
            + iv.normalize("23:00", "07:00")
        )
        assert iv.duration(windows) == 24 * 60


class TestCoverage:
    def test_full(self):
        avail = iv.normalize("07:00", "19:00")
        cov = iv.coverage("07:00", "15:00", avail)
        assert cov["state"] == "full"
        assert cov["gaps"] == []

    def test_none(self):
        avail = iv.normalize("07:00", "12:00")
        cov = iv.coverage("19:00", "07:00", avail)
        assert cov["state"] == "none"

    def test_partial_reports_gap(self):
        # Position 19:00–07:00; guard available only 19:00–01:00 → gap 01:00–07:00.
        avail = iv.normalize("19:00", "01:00")
        cov = iv.coverage("19:00", "07:00", avail)
        assert cov["state"] == "partial"
        # gap is 01:00–07:00 = 6h.
        assert sum(e - s for s, e in cov["gaps"]) == 6 * 60
        gap_s, gap_e = cov["gaps"][0]
        assert iv.to_hhmm(gap_s) == "01:00"
        assert iv.to_hhmm(gap_e) == "07:00"


class TestSubtract:
    def test_gap_in_middle(self):
        window = iv.normalize("07:00", "19:00")
        avail = iv.normalize("09:00", "12:00")
        gaps = iv.subtract(window, avail)
        # remaining = 07:00–09:00 and 12:00–19:00
        assert iv.duration(gaps) == (2 + 7) * 60
