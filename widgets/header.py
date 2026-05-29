"""Dashboard header widget — clean with breathing room."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class DashboardHeader(Widget):
    DEFAULT_CSS = """
    DashboardHeader {
        height: auto;
        padding: 1 3;
        background: #2a4060;
    }

    DashboardHeader #title {
        width: 100%;
        height: 1;
        text-align: center;
    }

    DashboardHeader #spacer1 {
        width: 100%;
        height: 1;
    }

    DashboardHeader #sprint-row {
        width: 100%;
        height: 1;
        text-align: center;
    }

    DashboardHeader #refresh-row {
        width: 100%;
        height: 1;
        text-align: center;
    }
    """

    sprint_name: reactive[str] = reactive("")
    sprint_dates: reactive[str] = reactive("")
    last_refresh: reactive[str] = reactive("Never")
    next_refresh: reactive[str] = reactive("")
    tag_filter: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("\u2692 [bold]Tarik's Dashboard[/]", id="title")
        yield Static("", id="spacer1")
        yield Static("", id="sprint-row")
        yield Static("", id="refresh-row")

    def watch_sprint_name(self) -> None:
        self._update_info()

    def watch_sprint_dates(self) -> None:
        self._update_info()

    def watch_tag_filter(self) -> None:
        self._update_info()

    def watch_last_refresh(self) -> None:
        self._update_info()

    def watch_next_refresh(self) -> None:
        self._update_info()

    def _update_info(self) -> None:
        # Sprint info row
        try:
            sprint_row = self.query_one("#sprint-row", Static)
            parts: list[str] = []
            if self.sprint_name:
                parts.append(f"\U0001f3c3 [#a3be8c]{self.sprint_name}[/]")
            if self.sprint_dates:
                parts.append(f"\U0001f4c5 [#90a8c0]{self.sprint_dates}[/]")
            if self.tag_filter:
                parts.append(f"\U0001f3f7 [#88b8e0]{self.tag_filter}[/]")
            sprint_row.update("    ".join(parts))
        except Exception:
            pass

        # Refresh info row
        try:
            refresh_row = self.query_one("#refresh-row", Static)
            parts = []
            if self.last_refresh:
                parts.append(f"\u21bb [#80a0b8]Last refresh: {self.last_refresh}[/]")
            if self.next_refresh:
                parts.append(f"\u23f1 [#7090a8]Next: {self.next_refresh}[/]")
            refresh_row.update("    ".join(parts))
        except Exception:
            pass
