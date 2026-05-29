"""Data models for the ADO Sprint Dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


def _sort_date(dt: datetime | None) -> datetime:
    """Normalize a datetime for sorting — strip tzinfo so naive/aware never mix."""
    if dt is None:
        return datetime.min
    return dt.replace(tzinfo=None)


class WorkItemState(Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    NEW = "New"
    REMOVED = "Removed"

    @property
    def is_done(self) -> bool:
        return self in (WorkItemState.RESOLVED, WorkItemState.CLOSED)

    @property
    def is_active(self) -> bool:
        return self == WorkItemState.IN_PROGRESS

    @property
    def is_blocked(self) -> bool:
        return self == WorkItemState.BLOCKED

    @property
    def display(self) -> str:
        return self.value

    @classmethod
    def from_str(cls, s: str) -> WorkItemState:
        for member in cls:
            if member.value.lower() == s.strip().lower():
                return member
        return cls.OPEN


def ado_item_url(item_id: int) -> str:
    """Build a browser URL for a work item using the active config."""
    from config import get_active
    return f"{get_active().work_item_base_url}/{item_id}"


@dataclass
class WorkItem:
    id: int
    title: str
    work_item_type: str  # "Enabling Specification" or "Task"
    state: WorkItemState
    tags: list[str] = field(default_factory=list)
    area_path: str = ""
    iteration_path: str = ""
    child_ids: list[int] = field(default_factory=list)
    parent_id: int | None = None
    completed_in_sprint: str | None = None  # e.g. "Sprint 5" if done in a different sprint
    state_changed_date: datetime | None = None  # for sorting Done items by recency

    @property
    def url(self) -> str:
        return ado_item_url(self.id)

    @property
    def is_enabling_spec(self) -> bool:
        return self.work_item_type == "Enabling Specification"

    @property
    def is_task(self) -> bool:
        return self.work_item_type == "Task"


@dataclass
class EnablingSpec:
    """An Enabling Specification with its child tasks."""
    item: WorkItem
    tasks: list[WorkItem] = field(default_factory=list)

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.state.is_done)

    @property
    def in_progress_count(self) -> int:
        return sum(1 for t in self.tasks if t.state.is_active)

    @property
    def blocked_count(self) -> int:
        return sum(1 for t in self.tasks if t.state.is_blocked)

    @property
    def open_count(self) -> int:
        return sum(1 for t in self.tasks if t.state in (WorkItemState.OPEN, WorkItemState.NEW))

    @property
    def total_count(self) -> int:
        return len(self.tasks)

    @property
    def progress(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.done_count / self.total_count


@dataclass
class Sprint:
    id: str
    name: str
    path: str
    start_date: datetime | None = None
    finish_date: datetime | None = None

    @property
    def date_range(self) -> str:
        if self.start_date and self.finish_date:
            return (
                f"{self.start_date.strftime('%b %d')} - "
                f"{self.finish_date.strftime('%b %d, %Y')}"
            )
        return ""


@dataclass
class DashboardData:
    """All data needed to render the dashboard."""
    sprint: Sprint
    enabling_specs: list[EnablingSpec] = field(default_factory=list)
    standalone_tasks: list[WorkItem] = field(default_factory=list)
    last_refresh: datetime | None = None

    @property
    def all_items(self) -> list[WorkItem]:
        items: list[WorkItem] = []
        for es in self.enabling_specs:
            items.append(es.item)
            items.extend(es.tasks)
        items.extend(self.standalone_tasks)
        return items

    @property
    def blocked_items(self) -> list[WorkItem]:
        """All blocked items (specs + tasks), sorted most-recently-changed first."""
        items = [item for item in self.all_items if item.state.is_blocked]
        items.sort(
            key=lambda x: _sort_date(x.state_changed_date),
            reverse=True,
        )
        return items

    @property
    def in_progress_items(self) -> list[WorkItem]:
        """All in-progress items (specs + tasks), sorted most-recently-changed first."""
        items = [item for item in self.all_items if item.state == WorkItemState.IN_PROGRESS]
        items.sort(
            key=lambda x: _sort_date(x.state_changed_date),
            reverse=True,
        )
        return items

    @property
    def done_items(self) -> list[WorkItem]:
        """All resolved/closed items (specs + tasks), sorted most-recently-closed first."""
        items = [item for item in self.all_items if item.state.is_done]
        items.sort(
            key=lambda x: _sort_date(x.state_changed_date),
            reverse=True,
        )
        return items

    def count_by_state(self, state: WorkItemState) -> int:
        return sum(1 for item in self.all_items if item.state == state)

    @property
    def total_count(self) -> int:
        return len(self.all_items)

    @property
    def open_count(self) -> int:
        return self.count_by_state(WorkItemState.OPEN) + self.count_by_state(WorkItemState.NEW)

    @property
    def in_progress_count(self) -> int:
        return self.count_by_state(WorkItemState.IN_PROGRESS)

    @property
    def resolved_count(self) -> int:
        return self.count_by_state(WorkItemState.RESOLVED)

    @property
    def closed_count(self) -> int:
        return self.count_by_state(WorkItemState.CLOSED)
