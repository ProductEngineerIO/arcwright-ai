"""Output package — Run management, decision provenance, and summary generation."""

from __future__ import annotations

from arcwright_ai.output.provenance import append_entry, render_validation_row, write_entries
from arcwright_ai.output.run_manager import (
    RunStatus,
    RunStatusValue,
    RunSummary,
    StoryStatusEntry,
    create_run,
    generate_run_id,
    get_run_status,
    list_runs,
    update_run_status,
    update_story_status,
)
from arcwright_ai.output.summary import (
    write_halt_report,
    write_success_summary,
    write_timeout_summary,
)

__all__: list[str] = [
    "RunStatus",
    "RunStatusValue",
    "RunSummary",
    "StoryStatusEntry",
    "append_entry",
    "create_run",
    "generate_run_id",
    "get_run_status",
    "list_runs",
    "render_validation_row",
    "update_run_status",
    "update_story_status",
    "write_entries",
    "write_halt_report",
    "write_success_summary",
    "write_timeout_summary",
]
