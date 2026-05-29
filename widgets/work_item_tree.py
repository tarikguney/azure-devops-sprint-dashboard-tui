"""Work item tree widget with expand/collapse and keyboard navigation."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from models import DashboardData, EnablingSpec, WorkItem, WorkItemState


def _state_badge(state: WorkItemState) -> str:
    """Render a colored state badge."""
    colors = {
        WorkItemState.OPEN: ("#e0e0e0", "#4a4a4a"),
        WorkItemState.NEW: ("#e0e0e0", "#4a4a4a"),
        WorkItemState.IN_PROGRESS: ("#1a1a1a", "#c8a855"),
        WorkItemState.BLOCKED: ("#f0f0f0", "#b05050"),
        WorkItemState.RESOLVED: ("#1a1a1a", "#5f9ea0"),
        WorkItemState.CLOSED: ("#f0f0f0", "#5a8a5a"),
        WorkItemState.REMOVED: ("#b0b0b0", "#3a3a3a"),
    }
    fg, bg = colors.get(state, ("#e0e0e0", "#4a4a4a"))
    padded = f" {state.display:^11s} "
    return f"[{fg} on {bg}]{padded}[/]"


def _task_counts(done: int, in_prog: int, blocked: int, open_count: int) -> str:
    """Render compact task state counts: done (green), in-progress (yellow), blocked (red), open (gray)."""
    parts = [f"[#80e080]{done}[/]", f"[#f0d050]{in_prog}[/]"]
    if blocked:
        parts.append(f"[#e06060]{blocked}[/]")
    parts.append(f"[#b0b0b0]{open_count}[/]")
    return " ".join(parts)


def _tag_badges(item: WorkItem) -> str:
    """Render WT/T tag badges for an item."""
    tags_lower = [t.lower() for t in item.tags]
    badges: list[str] = []
    if "weeklytarget" in tags_lower:
        badges.append("[#1a1a1a on #e6b800] WT [/]")
    if "triage" in tags_lower:
        badges.append("[#1a1a1a on #c8a855] T [/]")
    return " ".join(badges) + " " if badges else ""


def _work_item_id(item: WorkItem) -> str:
    """Render a work item ID with color, fixed width."""
    return f"[#5fafd7]#{item.id:<8d}[/]"


class WorkItemRow(Static):
    """A single row in the work item tree."""

    class Selected(Message):
        def __init__(self, row: WorkItemRow) -> None:
            super().__init__()
            self.row = row

    class ToggleExpand(Message):
        def __init__(self, row: WorkItemRow) -> None:
            super().__init__()
            self.row = row

    class StatusChange(Message):
        def __init__(self, work_item_id: int, new_state: WorkItemState) -> None:
            super().__init__()
            self.work_item_id = work_item_id
            self.new_state = new_state

    # Store the underlying data
    work_item_id: int = 0
    work_item_state: WorkItemState = WorkItemState.OPEN
    is_spec: bool = False
    is_expanded: bool = False
    is_child: bool = False
    is_last_child: bool = False

    def __init__(
        self,
        item: WorkItem,
        is_child: bool = False,
        is_last_child: bool = False,
        parent_expanded: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.work_item_id = item.id
        self.work_item_state = item.state
        self.is_spec = item.is_enabling_spec
        self.is_child = is_child
        self.is_last_child = is_last_child
        self._item = item

    def render_content(
        self,
        expanded: bool = False,
        done: int = 0,
        in_prog: int = 0,
        blocked: int = 0,
        open_count: int = 0,
        total: int = 0,
        flat_done: bool = False,
        show_spec_tags: bool = False,
    ) -> str:
        parts: list[str] = []

        if flat_done:
            # Flat done row: type tag + badge + id + title + date
            if self._item.is_enabling_spec:
                parts.append("[#1a1a1a on #7a6f9a] ES [/] ")
            else:
                parts.append("[#1a1a1a on #5a8a9a]  T [/] ")
            parts.append(_state_badge(self.work_item_state))
            parts.append("  ")
            parts.append(_work_item_id(self._item))
            parts.append("  ")
            parts.append(self._item.title.replace("[", "\\["))
            if self._item.state_changed_date:
                date_str = self._item.state_changed_date.strftime("%b %d")
                parts.append(f"  [dim italic]{date_str}[/]")
            if self._item.completed_in_sprint:
                parts.append(f"  [dim italic]in {self._item.completed_in_sprint}[/]")
            return "".join(parts)

        # Indent and tree connector (4 chars fixed width for all paths)
        if self.is_child:
            connector = "`-- " if self.is_last_child else "|-- "
            parts.append(f"    [dim]{connector}[/]")
        elif self.is_spec and total > 0:
            arrow = " v  " if expanded else " >  "
            parts.append(f"[bold]{arrow}[/]")
        else:
            parts.append("    ")

        # State badge
        parts.append(_state_badge(self.work_item_state))

        # Task counts (right after badge, for all specs)
        if self.is_spec:
            parts.append("  ")
            parts.append(_task_counts(done, in_prog, blocked, open_count))

        parts.append("  ")

        # Tag badges (child tasks always; specs only when filter is off)
        if self.is_child or (self.is_spec and show_spec_tags):
            parts.append(_tag_badges(self._item))

        # Work item ID
        parts.append(_work_item_id(self._item))
        parts.append("  ")

        # Title
        title = self._item.title.replace("[", "\\[")
        if self.is_spec:
            parts.append(f"[bold]{title}[/]")
        else:
            parts.append(title)

        # Cross-sprint annotation
        if self._item.completed_in_sprint and self._item.state.is_done:
            state_label = self._item.state.display
            parts.append(f"  [dim italic]{state_label} in {self._item.completed_in_sprint}[/]")

        return "".join(parts)


class WorkItemTree(Widget):
    """Navigable tree of work items with expand/collapse."""

    DEFAULT_CSS = """
    WorkItemTree {
        height: 1fr;
        padding: 0 1;
    }

    WorkItemTree VerticalScroll {
        height: 1fr;
    }

    WorkItemTree .section-header {
        color: $text;
        text-style: bold;
        margin: 1 0 0 0;
        padding: 0 0;
    }

    WorkItemTree .section-divider {
        color: $text-muted;
        margin: 0 0 0 0;
    }

    WorkItemTree .work-item-row {
        height: 1;
        padding: 0 1;
    }

    WorkItemTree .work-item-row:hover {
        background: #1e2a3a;
    }

    WorkItemTree .work-item-row.--selected {
        background: #5a4520;
    }

    WorkItemTree .work-item-row.--child-row {
        padding-left: 2;
    }

    WorkItemTree .empty-state {
        text-align: center;
        color: $text-muted;
        margin: 2 0;
    }
    """

    BINDINGS = [
        Binding("up,k", "cursor_up", "Up", show=False),
        Binding("down,j", "cursor_down", "Down", show=False),
        Binding("enter,space", "toggle_expand", "Expand/Collapse", show=False),
        Binding("home", "cursor_home", "Home", show=False),
        Binding("end", "cursor_end", "End", show=False),
    ]

    selected_index: reactive[int] = reactive(0)

    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._data: DashboardData | None = None
        self._expanded: set[int] = set()  # IDs of expanded enabling specs
        self._visible_rows: list[WorkItemRow] = []
        self._filter_text: str = ""
        self._loading: bool = False
        self._show_spec_tags: bool = False

    def set_loading(self, loading: bool = True) -> None:
        """Show or hide the loading indicator."""
        self._loading = loading
        if loading:
            try:
                scroll = self.query_one(VerticalScroll)
                scroll.remove_children()
                self._visible_rows.clear()
                scroll.mount(Static("[dim italic]Fetching work items from ADO...[/]", classes="empty-state"))
            except Exception:
                pass

    def update_data(self, data: DashboardData) -> None:
        """Update the tree with new data, preserving expand/filter state."""
        self._loading = False
        self._data = data
        self._rebuild()

    def set_show_spec_tags(self, show: bool) -> None:
        """Toggle whether enabling spec rows render their tag badges."""
        if self._show_spec_tags != show:
            self._show_spec_tags = show
            self._rebuild()

    def set_filter(self, text: str) -> None:
        """Filter items by title."""
        self._filter_text = text.lower().strip()
        self._rebuild()

    def clear_filter(self) -> None:
        self._filter_text = ""
        self._rebuild()

    def expand_all(self) -> None:
        if self._data:
            self._expanded = {es.item.id for es in self._data.enabling_specs}
            self._rebuild()

    def collapse_all(self) -> None:
        self._expanded.clear()
        self._rebuild()

    def get_selected_work_item_id(self) -> int | None:
        if 0 <= self.selected_index < len(self._visible_rows):
            return self._visible_rows[self.selected_index].work_item_id
        return None

    def get_selected_state(self) -> WorkItemState | None:
        if 0 <= self.selected_index < len(self._visible_rows):
            return self._visible_rows[self.selected_index].work_item_state
        return None

    def get_selected_title(self) -> str | None:
        if 0 <= self.selected_index < len(self._visible_rows):
            return self._visible_rows[self.selected_index]._item.title
        return None

    def update_item_title(self, work_item_id: int, new_title: str) -> None:
        """Optimistically update a work item's title in local data."""
        if not self._data:
            return
        for es in self._data.enabling_specs:
            if es.item.id == work_item_id:
                es.item.title = new_title
                self._rebuild()
                return
            for task in es.tasks:
                if task.id == work_item_id:
                    task.title = new_title
                    self._rebuild()
                    return
        for task in self._data.standalone_tasks:
            if task.id == work_item_id:
                task.title = new_title
                self._rebuild()
                return

    def get_parent_spec_id(self) -> int | None:
        """Get the enabling spec ID for the selected row.

        If the selected row IS a spec, returns its ID.
        If the selected row is a child task, returns its parent spec ID.
        Returns None if no parent spec can be determined.
        """
        if not self._data or not (0 <= self.selected_index < len(self._visible_rows)):
            return None
        row = self._visible_rows[self.selected_index]
        if row.is_spec:
            return row.work_item_id
        # It's a task — find its parent spec
        wid = row.work_item_id
        for es in self._data.enabling_specs:
            if any(t.id == wid for t in es.tasks):
                return es.item.id
        return None

    def _rebuild(self) -> None:
        """Rebuild the tree widget from current data + expand state."""
        if self._loading:
            # Keep the "Fetching..." placeholder visible until new data arrives.
            return

        scroll = None
        try:
            scroll = self.query_one(VerticalScroll)
        except Exception:
            return

        scroll.remove_children()
        self._visible_rows.clear()

        if not self._data:
            scroll.mount(Static("Loading...", classes="empty-state"))
            return

        data = self._data

        if not data.enabling_specs and not data.standalone_tasks:
            tag_msg = f" with tag '{self._data.sprint.name}'" if self._filter_text else ""
            scroll.mount(
                Static(
                    f"No items found in sprint{tag_msg}",
                    classes="empty-state",
                )
            )
            return

        # Filter indicator
        if self._filter_text:
            scroll.mount(Static(
                f"[bold #c8a855]Filtering:[/] [#e0e0e0]\"{self._filter_text}\"[/]",
                classes="section-header",
            ))

        # Enabling Specs section
        if data.enabling_specs:
            scroll.mount(Static("ENABLING SPECS", classes="section-header"))
            scroll.mount(Static("─" * max(self.size.width - 2, 20), classes="section-divider"))

            for es in data.enabling_specs:
                if not self._matches_filter(es):
                    continue

                expanded = es.item.id in self._expanded
                row = WorkItemRow(
                    es.item,
                    classes="work-item-row",
                )
                row.update(row.render_content(
                    expanded=expanded,
                    done=es.done_count,
                    in_prog=es.in_progress_count,
                    blocked=es.blocked_count,
                    open_count=es.open_count,
                    total=es.total_count,
                    show_spec_tags=self._show_spec_tags,
                ))
                self._visible_rows.append(row)
                scroll.mount(row)

                if expanded:
                    state_order = {
                        WorkItemState.IN_PROGRESS: 0,
                        WorkItemState.BLOCKED: 1,
                        WorkItemState.OPEN: 2,
                        WorkItemState.NEW: 2,
                        WorkItemState.RESOLVED: 3,
                        WorkItemState.CLOSED: 4,
                        WorkItemState.REMOVED: 5,
                    }
                    sorted_tasks = sorted(
                        es.tasks,
                        key=lambda t: (state_order.get(t.state, 99), t.id),
                    )
                    for idx, task in enumerate(sorted_tasks):
                        if self._filter_text and self._filter_text not in task.title.lower():
                            continue
                        is_last = idx == len(sorted_tasks) - 1
                        child_row = WorkItemRow(
                            task,
                            is_child=True,
                            is_last_child=is_last,
                            classes="work-item-row --child-row",
                        )
                        child_row.update(child_row.render_content())
                        self._visible_rows.append(child_row)
                        scroll.mount(child_row)

        # Standalone Tasks section
        if data.standalone_tasks:
            standalone_filtered = [
                t for t in data.standalone_tasks
                if not self._filter_text or self._filter_text in t.title.lower()
            ]
            if standalone_filtered:
                scroll.mount(Static("", classes="section-header"))
                scroll.mount(Static("STANDALONE TASKS", classes="section-header"))
                scroll.mount(Static("─" * max(self.size.width - 2, 20), classes="section-divider"))

                for task in standalone_filtered:
                    row = WorkItemRow(task, classes="work-item-row")
                    row.update(row.render_content())
                    self._visible_rows.append(row)
                    scroll.mount(row)

        # In Progress section — flat list of all active items
        in_progress_items = data.in_progress_items
        if in_progress_items:
            ip_filtered = [
                item for item in in_progress_items
                if not self._filter_text or self._filter_text in item.title.lower()
            ]
            if ip_filtered:
                scroll.mount(Static("", classes="section-header"))
                scroll.mount(Static("IN PROGRESS", classes="section-header"))
                scroll.mount(Static("\u2500" * max(self.size.width - 2, 20), classes="section-divider"))

                for item in ip_filtered:
                    row = WorkItemRow(item, classes="work-item-row")
                    row.update(row.render_content(flat_done=True))
                    self._visible_rows.append(row)
                    scroll.mount(row)

        # Blocked section — flat list of all blocked items
        blocked_items = data.blocked_items
        if blocked_items:
            bl_filtered = [
                item for item in blocked_items
                if not self._filter_text or self._filter_text in item.title.lower()
            ]
            if bl_filtered:
                scroll.mount(Static("", classes="section-header"))
                scroll.mount(Static("BLOCKED", classes="section-header"))
                scroll.mount(Static("\u2500" * max(self.size.width - 2, 20), classes="section-divider"))

                for item in bl_filtered:
                    row = WorkItemRow(item, classes="work-item-row")
                    row.update(row.render_content(flat_done=True))
                    self._visible_rows.append(row)
                    scroll.mount(row)

        # Done section — flat chronological list of all resolved/closed items
        done_items = data.done_items
        if done_items:
            done_filtered = [
                item for item in done_items
                if not self._filter_text or self._filter_text in item.title.lower()
            ]
            if done_filtered:
                scroll.mount(Static("", classes="section-header"))
                scroll.mount(Static("DONE", classes="section-header"))
                scroll.mount(Static("─" * max(self.size.width - 2, 20), classes="section-divider"))

                for item in done_filtered:
                    row = WorkItemRow(item, classes="work-item-row")
                    row.update(row.render_content(flat_done=True))
                    self._visible_rows.append(row)
                    scroll.mount(row)

        # Clamp selection
        if self._visible_rows:
            self.selected_index = min(self.selected_index, len(self._visible_rows) - 1)
            self._highlight_selected()
        else:
            self.selected_index = 0

    def _matches_filter(self, es: EnablingSpec) -> bool:
        """Check if an enabling spec or any of its tasks match the filter."""
        if not self._filter_text:
            return True
        if self._filter_text in es.item.title.lower():
            return True
        return any(self._filter_text in t.title.lower() for t in es.tasks)

    def _highlight_selected(self) -> None:
        """Update CSS classes to highlight the selected row."""
        for i, row in enumerate(self._visible_rows):
            if i == self.selected_index:
                row.add_class("--selected")
            else:
                row.remove_class("--selected")

    def watch_selected_index(self) -> None:
        self._highlight_selected()
        # Scroll the selected row into view
        if 0 <= self.selected_index < len(self._visible_rows):
            row = self._visible_rows[self.selected_index]
            row.scroll_visible()

    def action_cursor_up(self) -> None:
        if self._visible_rows and self.selected_index > 0:
            self.selected_index -= 1

    def action_cursor_down(self) -> None:
        if self._visible_rows and self.selected_index < len(self._visible_rows) - 1:
            self.selected_index += 1

    def action_cursor_home(self) -> None:
        if self._visible_rows:
            self.selected_index = 0

    def action_cursor_end(self) -> None:
        if self._visible_rows:
            self.selected_index = len(self._visible_rows) - 1

    def action_toggle_expand(self) -> None:
        if not self._visible_rows:
            return
        row = self._visible_rows[self.selected_index]
        if row.is_spec:
            wid = row.work_item_id
            if wid in self._expanded:
                self._expanded.discard(wid)
            else:
                self._expanded.add(wid)
            self._rebuild()

    def update_item_state(self, work_item_id: int, new_state: WorkItemState) -> None:
        """Optimistically update a work item's state in local data."""
        if not self._data:
            return
        for es in self._data.enabling_specs:
            if es.item.id == work_item_id:
                es.item.state = new_state
                self._rebuild()
                return
            for task in es.tasks:
                if task.id == work_item_id:
                    task.state = new_state
                    self._rebuild()
                    return
        for task in self._data.standalone_tasks:
            if task.id == work_item_id:
                task.state = new_state
                self._rebuild()
                return

    def compose(self) -> ComposeResult:
        vs = VerticalScroll()
        vs.can_focus = False
        yield vs

    def on_mount(self) -> None:
        self.focus()
