"""Three-line progress bar with vertically centered labels."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatusLine(Widget):
    """Three-line progress bar: blank, labels centered, blank."""

    DEFAULT_CSS = """
    StatusLine {
        height: auto;
        padding: 0 2;
        margin: 1 0 0 0;
    }

    StatusLine .bar-row {
        width: 100%;
        height: 1;
    }
    """

    total: reactive[int] = reactive(0)
    open_count: reactive[int] = reactive(0)
    in_progress: reactive[int] = reactive(0)
    blocked_count: reactive[int] = reactive(0)
    done_count: reactive[int] = reactive(0)
    loading: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static("", classes="bar-row", id="bar-top")
        yield Static("", classes="bar-row", id="bar-mid")
        yield Static("", classes="bar-row", id="bar-bot")

    def watch_total(self) -> None:
        self._redraw()

    def watch_open_count(self) -> None:
        self._redraw()

    def watch_in_progress(self) -> None:
        self._redraw()

    def watch_blocked_count(self) -> None:
        self._redraw()

    def watch_done_count(self) -> None:
        self._redraw()

    def watch_loading(self) -> None:
        self._redraw()

    def _make_blank(self, done_w: int, prog_w: int, blocked_w: int, open_w: int) -> str:
        return (
            f"[on #7ec87e]{' ' * done_w}[/]"
            f"[on #e0b854]{' ' * prog_w}[/]"
            f"[on #c05050]{' ' * blocked_w}[/]"
            f"[on #2e3340]{' ' * open_w}[/]"
        )

    def _make_segment(self, width: int, label: str, fg: str, bg: str) -> str:
        if width <= 0:
            return ""
        if len(label) <= width:
            text = label.center(width)
        else:
            text = " " * width
        return f"[{fg} on {bg}]{text}[/]"

    def _redraw(self) -> None:
        try:
            bar_top = self.query_one("#bar-top", Static)
            bar_mid = self.query_one("#bar-mid", Static)
            bar_bot = self.query_one("#bar-bot", Static)
        except Exception:
            return

        if self.loading:
            bar_top.update("")
            bar_mid.update("")
            bar_bot.update("")
            return

        total = self.total
        if total == 0:
            bar_top.update("")
            bar_mid.update("[dim]No items[/]")
            bar_bot.update("")
            return

        bar_width = max(self.size.width - 4, 20)

        done_w = round(self.done_count / total * bar_width)
        prog_w = round(self.in_progress / total * bar_width)
        blocked_w = round(self.blocked_count / total * bar_width)
        open_w = bar_width - done_w - prog_w - blocked_w

        # Top & bottom: plain colored rows
        blank = self._make_blank(done_w, prog_w, blocked_w, open_w)
        bar_top.update(blank)
        bar_bot.update(blank)

        # Middle: labels centered inside each segment
        pct = round(self.done_count / total * 100)
        done_label = f"{self.done_count} done ({pct}%)"
        prog_label = f"{self.in_progress} active"
        blocked_label = f"{self.blocked_count} blocked"
        open_label = f"{self.open_count} open"

        mid = (
            self._make_segment(done_w, done_label, "#1a1a1a", "#7ec87e")
            + self._make_segment(prog_w, prog_label, "#1a1a1a", "#e0b854")
            + self._make_segment(blocked_w, blocked_label, "#f0f0f0", "#c05050")
            + self._make_segment(open_w, open_label, "#8a8f9e", "#2e3340")
        )
        bar_mid.update(mid)

    def on_resize(self) -> None:
        self._redraw()
