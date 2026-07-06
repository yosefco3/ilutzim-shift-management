#!/usr/bin/env python3
"""
Test Graph Generator - Maps test files to source files and shows test status.

Usage:
    python scripts/test_graph.py              # Run tests + generate TEST_GRAPH.md (default)
    python scripts/test_graph.py --no-run     # Generate TEST_GRAPH.md without running tests
    python scripts/test_graph.py --json       # Run tests + output JSON to stdout
    python scripts/test_graph.py --json --no-run  # Output JSON without running tests

Output: TEST_GRAPH.md (or JSON to stdout with --json)
History: scripts/test_history.json (last 50 runs)
"""

import ast
import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
HISTORY_PATH = Path(__file__).resolve().parent / "test_history.json"
MAX_HISTORY = 50


def backend_python() -> str:
    """Return the Python interpreter that has the backend deps installed.

    The app + pytest live in ``backend/.venv`` — ``sys.executable`` may be a bare
    system python without them (which silently yields 0 backend results).  Prefer
    the venv interpreter, fall back to whatever is running this script.
    """
    venv_py = BACKEND_DIR / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.exists() else sys.executable

# ── Backend mapping ──────────────────────────────────────────

BACKEND_SOURCE_DIRS = [
    "app/models",
    "app/repositories",
    "app/services",
    "app/controllers",
    "app/schemas",
    "app/bot",
    "app/utils",
    "app",
]

BACKEND_TEST_DIR = "tests"

# Manual overrides: test_file -> [source_files]
BACKEND_MANUAL_MAP = {
    "test_health.py": ["app/main.py"],
    "test_config.py": ["app/config.py"],
    "test_bot.py": ["app/bot/bot_router.py", "app/bot/core.py", "app/bot/notifications.py", "app/bot/cron.py"],
    "test_models.py": [
        "app/models/user.py", "app/models/admin.py", "app/models/schedule_event.py",
        "app/models/schedule_week.py", "app/models/weekly_submission.py",
        "app/models/daily_status.py", "app/models/shift_window.py", "app/models/system_setting.py",
    ],
    "test_repositories.py": [
        "app/repositories/user_repository.py", "app/repositories/admin_repository.py",
        "app/repositories/schedule_event_repository.py", "app/repositories/schedule_week_repository.py",
        "app/repositories/submission_repository.py", "app/repositories/system_settings_repository.py",
    ],
    "test_controllers.py": [
        "app/controllers/auth_controller.py", "app/controllers/submission_controller.py",
        "app/controllers/admin_users_controller.py", "app/controllers/admin_weeks_controller.py",
        "app/controllers/admin_events_controller.py", "app/controllers/admin_notifications_controller.py",
        "app/controllers/admin_export_controller.py",
    ],
    "test_schemas.py": [
        "app/schemas/user_schemas.py", "app/schemas/week_schemas.py",
        "app/schemas/submission_schemas.py", "app/schemas/event_schemas.py",
        "app/schemas/common_schemas.py",
    ],
    "test_export.py": ["app/services/excel_export_service.py", "app/controllers/admin_export_controller.py"],
    "test_date_utils.py": ["app/utils/date_utils.py"],
    "test_current_week.py": ["app/services/week_service.py", "app/repositories/schedule_week_repository.py"],
    "test_open_week.py": ["app/services/week_service.py", "app/controllers/admin_weeks_controller.py"],
    "test_status_transitions.py": ["app/services/week_service.py", "app/constants.py"],
    "test_week_workflow.py": ["app/services/week_service.py", "app/repositories/schedule_week_repository.py"],
    "test_initial_seed.py": ["app/seed.py"],
    "test_notification_on_open.py": ["app/bot/notifications.py", "app/services/week_service.py"],
    "test_submission_guard.py": ["app/controllers/submission_controller.py", "app/services/week_service.py"],
    "test_e2e.py": ["app/main.py"],
}

# ── Frontend mapping ─────────────────────────────────────────

FRONTEND_MANUAL_MAP = {
    # admin
    "admin/tests/apiClient.test.js": ["admin/src/api/adminApiClient.js"],
    "admin/tests/messages.test.js": ["admin/src/utils/messages.js"],
    "admin/tests/components.test.jsx": [
        "admin/src/components/EventForm.jsx",
        "admin/src/components/ProtectedRoute.jsx",
        "admin/src/components/StatusGrid.jsx",
        "admin/src/components/Navbar.jsx",
        "admin/src/components/WeekStatusControl.jsx",
        "admin/src/components/ConfirmDialog.jsx",
        "admin/src/components/GuardForm.jsx",
        "admin/src/components/GuardTable.jsx",
    ],
}

# ── Priority Ranking ─────────────────────────────────────────

PRIORITY_RULES = [
    # (pattern, priority_label, icon)
    # HIGH: business logic
    ("app/services/", "HIGH", "🔴"),
    ("app/controllers/", "HIGH", "🔴"),
    ("app/repositories/", "HIGH", "🔴"),
    # MEDIUM: helpers
    ("app/utils/", "MEDIUM", "🟡"),
    ("app/schemas/", "MEDIUM", "🟡"),
    ("app/bot/handlers/", "MEDIUM", "🟡"),
    ("app/bot/middlewares/", "MEDIUM", "🟡"),
    ("app/bot/cron/", "MEDIUM", "🟡"),
    ("app/bot/keyboards/", "MEDIUM", "🟡"),
    # LOW: infrastructure
    ("app/models/base.py", "LOW", "⚪"),
    ("app/config.py", "LOW", "⚪"),
    ("app/logging_config.py", "LOW", "⚪"),
    ("app/constants.py", "LOW", "⚪"),
    ("app/exceptions.py", "LOW", "⚪"),
    ("app/database.py", "LOW", "⚪"),
    ("app/dependencies.py", "LOW", "⚪"),
    ("app/messages.py", "LOW", "⚪"),
    ("app/__init__.py", "LOW", "⚪"),
    ("app/bot/__init__.py", "LOW", "⚪"),
    ("app/bot/bot_instance.py", "LOW", "⚪"),
]

LOW_FILES = {
    "base.py", "config.py", "logging_config.py", "constants.py",
    "exceptions.py", "database.py", "dependencies.py", "messages.py",
    "__init__.py", "bot_instance.py",
}


def get_priority(src_path: str) -> tuple[str, str]:
    """Return (priority_label, icon) for a source file path."""
    for pattern, label, icon in PRIORITY_RULES:
        if pattern in src_path:
            return label, icon
    # Default: if file name is in LOW_FILES set, mark LOW
    basename = src_path.rsplit("/", 1)[-1]
    if basename in LOW_FILES:
        return "LOW", "⚪"
    # Remaining files that don't match any rule
    return "MEDIUM", "🟡"


# ── File discovery ───────────────────────────────────────────


def get_all_source_files() -> list[str]:
    """Get all backend source .py files."""
    files = []
    for d in BACKEND_SOURCE_DIRS:
        full = BACKEND_DIR / d
        if full.is_file() and full.suffix == ".py" and full.name != "__init__.py":
            files.append(d + "/" + full.name if "/" not in d else str(full.relative_to(BACKEND_DIR)))
        elif full.is_dir():
            for f in full.rglob("*.py"):
                if f.name == "__init__.py":
                    continue
                rel = str(f.relative_to(BACKEND_DIR))
                files.append(rel)
    return sorted(set(files))


def get_all_test_files() -> list[str]:
    """Get all backend test .py files."""
    test_dir = BACKEND_DIR / BACKEND_TEST_DIR
    files = []
    for f in test_dir.glob("test_*.py"):
        files.append(f.name)
    return sorted(files)


# ── Test runners ─────────────────────────────────────────────


def run_backend_tests() -> dict[str, str]:
    """Run pytest and collect per-test status."""
    results = {}
    try:
        cmd = [
            backend_python(), "-m", "pytest",
            "--tb=no", "-v", "--no-header",
            str(BACKEND_DIR / "tests"),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BACKEND_DIR), timeout=120)
        output = proc.stdout + proc.stderr

        for line in output.splitlines():
            m = re.match(r"(tests/)?(test_\w+\.py)::\S+\s+(PASSED|FAILED|ERROR)", line.strip())
            if m:
                _, test_file, status = m.groups()
                if test_file in results:
                    if status in ("FAILED", "ERROR"):
                        results[test_file] = status
                else:
                    results[test_file] = status

        for line in output.splitlines():
            m = re.match(r"(PASSED|FAILED|ERROR)\s+(tests/)?(test_\w+\.py)", line.strip())
            if m:
                status, _, test_file = m.groups()
                if test_file in results:
                    if status in ("FAILED", "ERROR"):
                        results[test_file] = status
                else:
                    results[test_file] = status

    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"Warning: Could not run backend tests: {e}", file=sys.stderr)

    return results


def run_frontend_tests(subdir: str) -> dict[str, str]:
    """Run vitest in a frontend subdir and collect results."""
    results = {}
    pkg_dir = FRONTEND_DIR / subdir
    try:
        cmd = ["npx", "vitest", "run", "--reporter=verbose"]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(pkg_dir), timeout=120)
        output = proc.stdout + proc.stderr
        for line in output.splitlines():
            m = re.match(r"\s*[✓✔]\s+(.*?\.test\.\w+)", line)
            if m:
                test_file = m.group(1).strip()
                basename = test_file.split("/")[-1]
                results[basename] = "PASS"
            m = re.match(r"\s*[×✗]\s+(.*?\.test\.\w+)", line)
            if m:
                test_file = m.group(1).strip()
                basename = test_file.split("/")[-1]
                results[basename] = "FAIL"
        for line in output.splitlines():
            m = re.match(r"\s*Test Files\s+(\d+)\s+passed\s+\((\d+)\)", line)
            if m:
                pass_count = int(m.group(1))
                total_count = int(m.group(2))
                if pass_count < total_count and not results:
                    results["_summary"] = f"PASS={pass_count}/{total_count}"
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"Warning: Could not run {subdir} tests: {e}", file=sys.stderr)
    return results


# ── Source-test mapping ──────────────────────────────────────


def build_source_test_map() -> dict[str, list[str]]:
    """Map source_file -> [test_files]."""
    mapping = defaultdict(list)
    for test_file, source_files in BACKEND_MANUAL_MAP.items():
        for src in source_files:
            mapping[src].append(test_file)
    return dict(mapping)


# ── Trend Tracker ────────────────────────────────────────────


def load_history() -> list[dict]:
    """Load test run history from JSON file."""
    if HISTORY_PATH.exists():
        try:
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_history(history: list[dict]) -> None:
    """Save test run history (keep last MAX_HISTORY entries)."""
    # Trim to max
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_run(
    backend_results: dict[str, str],
    frontend_results: dict[str, str],
    all_source_files: list[str],
    covered: list[str],
) -> dict:
    """Create a history record from the current run."""
    b_passed = sum(1 for v in backend_results.values() if v in ("PASSED", "PASS"))
    b_failed = sum(1 for v in backend_results.values() if v in ("FAILED", "FAIL", "ERROR"))
    b_total = b_passed + b_failed
    f_passed = sum(1 for k, v in frontend_results.items() if not k.startswith("_") and v == "PASS")
    f_failed = sum(1 for k, v in frontend_results.items() if not k.startswith("_") and v == "FAIL")
    f_total = f_passed + f_failed
    coverage_pct = len(covered) * 100 // max(len(all_source_files), 1)

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "backend_coverage%": coverage_pct,
        "backend_tests": b_total,
        "backend_passed": b_passed,
        "backend_failed": b_failed,
        "frontend_tests": f_total,
        "frontend_passed": f_passed,
        "frontend_failed": f_failed,
    }


def format_trend(current: dict, previous: dict | None) -> str:
    """Format trend indicator comparing current to previous run."""
    if previous is None:
        return ""
    delta = current["backend_coverage%"] - previous["backend_coverage%"]
    if delta > 0:
        return f" ↑{delta}%"
    elif delta < 0:
        return f" ↓{abs(delta)}%"
    return " →0%"


# ── Markdown generation ──────────────────────────────────────


def generate_markdown(
    source_test_map: dict[str, list[str]],
    backend_results: dict[str, str],
    frontend_results: dict[str, str],
    run_tests: bool,
    trend_info: str = "",
) -> str:
    """Generate the TEST_GRAPH.md content."""
    lines = []
    lines.append("# Test Coverage Graph")
    lines.append("")
    lines.append(f"_נוצר אוטומטית ב: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    if trend_info:
        lines.append(f"**טרנד:** {trend_info}")
    lines.append("")

    # Stats
    all_source_files = get_all_source_files()
    covered = [s for s in all_source_files if s in source_test_map]
    uncovered = [s for s in all_source_files if s not in source_test_map]
    coverage_pct = len(covered) * 100 // max(len(all_source_files), 1)

    lines.append("## סיכום")
    lines.append("")
    lines.append("| מדד | ערך |")
    lines.append("|---|---|")
    lines.append(f"| קבצי קוד backend | {len(all_source_files)} |")
    lines.append(f"| קבצי קוד מכוסים בטסטים | {len(covered)} |")
    lines.append(f"| קבצי קוד ללא טסטים | {len(uncovered)} |")
    lines.append(f"| אחוז כיסוי | {coverage_pct}%{trend_info} |")

    if run_tests and backend_results:
        passed = sum(1 for v in backend_results.values() if v == "PASSED" or v == "PASS")
        failed = sum(1 for v in backend_results.values() if v in ("FAILED", "FAIL", "ERROR"))
        lines.append(f"| טסטים עוברים (backend) | {passed} ✅ |")
        lines.append(f"| טסטים נכשלים (backend) | {failed} ❌ |")

    # Frontend stats
    fe_src_files = []
    for srcs in FRONTEND_MANUAL_MAP.values():
        fe_src_files.extend(srcs)
    fe_src_files = sorted(set(fe_src_files))
    fe_covered = len(fe_src_files)
    lines.append(f"| קבצי קוד frontend (ממופים) | {fe_covered} |")

    if run_tests and frontend_results:
        fe_passed = sum(1 for k, v in frontend_results.items() if not k.startswith("_") and v == "PASS")
        fe_failed = sum(1 for k, v in frontend_results.items() if not k.startswith("_") and v == "FAIL")
        lines.append(f"| טסטים עוברים (frontend) | {fe_passed} ✅ |")
        lines.append(f"| טסטים נכשלים (frontend) | {fe_failed} ❌ |")
    lines.append("")

    # Backend: Source → Tests mapping
    lines.append("## Backend: מיפוי קוד → טסטים")
    lines.append("")
    lines.append("| קובץ קוד | קובץ טסט | סטטוס |")
    lines.append("|---|---|---|")

    for src in sorted(source_test_map.keys()):
        test_files = source_test_map[src]
        for tf in sorted(test_files):
            if run_tests:
                status = backend_results.get(tf, "⚠️ NOT RUN")
                if status in ("PASSED", "PASS"):
                    icon = "🟢 PASS"
                elif status in ("FAILED", "FAIL"):
                    icon = "🔴 FAIL"
                elif status == "ERROR":
                    icon = "🔴 ERROR"
                else:
                    icon = "⚪ " + status
            else:
                icon = "—"
            src_short = src.replace("app/", "")
            lines.append(f"| `{src_short}` | `{tf}` | {icon} |")

    lines.append("")

    # Uncovered files with priority ranking
    if uncovered:
        lines.append("## Backend: קבצים ללא טסטים (מדורגים לפי חשיבות)")
        lines.append("")
        lines.append("| עדיפות | קובץ קוד | תיקייה |")
        lines.append("|---|---|---|")

        # Sort uncovered: HIGH first, then MEDIUM, then LOW
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        uncovered_with_priority = []
        for src in uncovered:
            label, icon = get_priority(src)
            uncovered_with_priority.append((priority_order[label], label, icon, src))
        uncovered_with_priority.sort(key=lambda x: (x[0], x[3]))

        for _, label, icon, src in uncovered_with_priority:
            parts = src.split("/")
            folder = "/".join(parts[:-1]) if len(parts) > 1 else "/"
            name = parts[-1]
            lines.append(f"| {icon} {label} | `{name}` | `{folder}` |")
        lines.append("")

    # Frontend
    lines.append("## Frontend: מיפוי טסטים")
    lines.append("")
    lines.append("| תת-פרויקט | קובץ קוד | קובץ טסט | סטטוס |")
    lines.append("|---|---|---|---|")

    for test_path, src_files in sorted(FRONTEND_MANUAL_MAP.items()):
        parts = test_path.split("/")
        subproject = parts[0]
        test_file = "/".join(parts[1:])
        for src in src_files:
            src_short = src.split("/", 1)[1] if "/" in src else src
            if run_tests:
                status = "—"
                for ft_key, ft_status in frontend_results.items():
                    if test_file in ft_key or ft_key.endswith(test_file.split("/")[-1]):
                        status = "🟢 PASS" if ft_status in ("PASS", "PASSED") else "🔴 FAIL"
                        break
            else:
                status = "—"
            lines.append(f"| {subproject} | `{src_short}` | `{test_file}` | {status} |")
    lines.append("")

    # Test files detail
    lines.append("## Backend: רשימת קבצי טסט")
    lines.append("")
    all_tests = get_all_test_files()
    lines.append("| קובץ טסט | מכסה קבצי קוד | סטטוס |")
    lines.append("|---|---|---|")
    for tf in all_tests:
        srcs = BACKEND_MANUAL_MAP.get(tf, ["(auto-detect)"])
        src_count = len(srcs)
        if run_tests:
            status = backend_results.get(tf, "⚪ NOT RUN")
            if "PASS" in status:
                icon = "🟢"
            elif "FAIL" in status or "ERROR" in status:
                icon = "🔴"
            else:
                icon = "⚪"
        else:
            icon = "—"
        lines.append(f"| `{tf}` | {src_count} | {icon} |")
    lines.append("")

    return "\n".join(lines)


# ── JSON generation ──────────────────────────────────────────


def generate_json(
    source_test_map: dict[str, list[str]],
    backend_results: dict[str, str],
    frontend_results: dict[str, str],
    run_tests: bool,
) -> dict:
    """Generate a JSON-serializable report."""
    all_source_files = get_all_source_files()
    covered = [s for s in all_source_files if s in source_test_map]
    uncovered = [s for s in all_source_files if s not in source_test_map]
    coverage_pct = len(covered) * 100 // max(len(all_source_files), 1)

    b_passed = sum(1 for v in backend_results.values() if v in ("PASSED", "PASS")) if run_tests else 0
    b_failed = sum(1 for v in backend_results.values() if v in ("FAILED", "FAIL", "ERROR")) if run_tests else 0
    f_passed = sum(1 for k, v in frontend_results.items() if not k.startswith("_") and v == "PASS") if run_tests else 0
    f_failed = sum(1 for k, v in frontend_results.items() if not k.startswith("_") and v == "FAIL") if run_tests else 0

    # Uncovered with priority
    uncovered_ranked = []
    for src in uncovered:
        label, icon = get_priority(src)
        uncovered_ranked.append({"file": src, "priority": label})

    # Backend mapping
    backend_map = []
    for src in sorted(source_test_map.keys()):
        test_files = source_test_map[src]
        for tf in sorted(test_files):
            status = backend_results.get(tf, None) if run_tests else None
            backend_map.append({"source": src, "test": tf, "status": status})

    # Frontend mapping
    frontend_map = []
    for test_path, src_files in sorted(FRONTEND_MANUAL_MAP.items()):
        parts = test_path.split("/")
        subproject = parts[0]
        test_file = "/".join(parts[1:])
        for src in src_files:
            status = None
            if run_tests:
                for ft_key, ft_status in frontend_results.items():
                    if test_file in ft_key or ft_key.endswith(test_file.split("/")[-1]):
                        status = ft_status
                        break
            frontend_map.append({
                "subproject": subproject,
                "source": src,
                "test": test_file,
                "status": status,
            })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "backend_source_files": len(all_source_files),
            "backend_covered": len(covered),
            "backend_uncovered": len(uncovered),
            "backend_coverage_pct": coverage_pct,
            "backend_passed": b_passed,
            "backend_failed": b_failed,
            "frontend_passed": f_passed,
            "frontend_failed": f_failed,
        },
        "uncovered_ranked": uncovered_ranked,
        "backend_mapping": backend_map,
        "frontend_mapping": frontend_map,
    }


# ── Main ─────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Graph Generator - Maps test files to source files and shows test status.",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        default=False,
        help="Generate report without running tests",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_output",
        help="Output JSON to stdout instead of generating TEST_GRAPH.md",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    run_tests = not args.no_run
    source_test_map = build_source_test_map()

    backend_results: dict[str, str] = {}
    frontend_results: dict[str, str] = {}

    if run_tests:
        print("Running backend tests...")
        backend_results = run_backend_tests()
        print(f"  Got {len(backend_results)} results")

        print("Running frontend admin tests...")
        admin_results = run_frontend_tests("admin")
        for k, v in admin_results.items():
            frontend_results[f"admin/{k}"] = v

    # ── Trend tracking (only when tests are run) ──
    trend_info = ""
    if run_tests:
        all_source_files = get_all_source_files()
        covered = [s for s in all_source_files if s in source_test_map]
        history = load_history()
        previous = history[-1] if history else None

        record = record_run(backend_results, frontend_results, all_source_files, covered)
        trend_info = format_trend(record, previous)

        history.append(record)
        save_history(history)

    # ── Output ──
    if args.json_output:
        report = generate_json(source_test_map, backend_results, frontend_results, run_tests)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        md = generate_markdown(source_test_map, backend_results, frontend_results, run_tests, trend_info)
        output_path = REPO_ROOT / "TEST_GRAPH.md"
        output_path.write_text(md, encoding="utf-8")
        print(f"\n✅ Generated: {output_path}")
        if trend_info:
            print(f"   Trend: {trend_info.strip()}")
        if run_tests:
            print(f"   Backend: {len(backend_results)} test results")
            print(f"   Frontend: {len(frontend_results)} test results")
        else:
            print("   Tip: Run without --no-run to include test pass/fail status")


if __name__ == "__main__":
    main()