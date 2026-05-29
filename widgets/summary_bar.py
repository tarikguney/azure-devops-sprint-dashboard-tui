"""Summary bar widget showing work item counts by state."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class CountBox(Static):
    DEFAULT_CSS = """
    CountBox {
        width: 1fr;
        height: 3;
        content-align: center middle;
        text-align: center;
        border: round $surface-lighten-2;
        margin: 0 1;
    }
    """


class SummaryBar(Widget):
    DEFAULT_CSS = """
    SummaryBar {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }

    SummaryBar Horizontal {
        height: auto;
        align: center middle;
    }

    SummaryBar .total-box { border: round $primary; }
    SummaryBar .open-box { border: round white; }
    SummaryBar .active-box { border: round yellow; }
    SummaryBar .resolved-box { border: round cyan; }
    SummaryBar .closed-box { border: round green; }
    """

    total: reactive[int] = reactive(0)
    open_count: reactive[int] = reactive(0)
    in_progress: reactive[int] = reactive(0)
    resolved: reactive[int] = reactive(0)
    closed: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield CountBox("Total\n[bold]0[/]", classes="total-box", id="total-box")
            yield CountBox("Open\n[bold]0[/]", classes="open-box", id="open-box")
            yield CountBox("Active\n[bold]0[/]", classes="active-box", id="active-box")
            yield CountBox("Resolved\n[bold]0[/]", classes="resolved-box", id="resolved-box")
            yield CountBox("Closed\n[bold]0[/]", classes="closed-box", id="closed-box")

    def watch_total(self) -> None:
        self._update_box("total-box", "Total", self.total, "bold bright_white")

    def watch_open_count(self) -> None:
        self._update_box("open-box", "Open", self.open_count, "bold white")

    def watch_in_progress(self) -> None:
        self._update_box("active-box", "Active", self.in_progress, "bold yellow")

    def watch_resolved(self) -> None:
        self._update_box("resolved-box", "Resolved", self.resolved, "bold bright_cyan")

    def watch_closed(self) -> None:
        self._update_box("closed-box", "Closed", self.closed, "bold bright_green")

    def _update_box(self, box_id: str, label: str, count: int, style: str) -> None:
        try:
            box = self.query_one(f"#{box_id}", CountBox)
            box.update(f"{label}\n[{style}]{count}[/]")
        except Exception:
            pass
