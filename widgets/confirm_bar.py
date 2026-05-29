"""Confirmation bar for status change actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from models import WorkItemState


class ConfirmBar(Widget):
    """Inline confirmation bar: 'Set #1234 to "In Progress"? (y/n)'"""

    DEFAULT_CSS = """
    ConfirmBar {
        display: none;
        dock: bottom;
        height: auto;
        padding: 1 3;
        background: #1e2a3a;
        border-top: solid #c8a855;
        border-bottom: solid #c8a855;
    }

    ConfirmBar.--visible {
        display: block;
    }

    ConfirmBar .confirm-text {
        color: #e0e0e0;
        text-style: bold;
        text-align: center;
        width: 100%;
        padding: 1 0;
    }
    """

    class Confirmed(Message):
        def __init__(self, work_item_id: int, new_state: WorkItemState) -> None:
            super().__init__()
            self.work_item_id = work_item_id
            self.new_state = new_state

    class Cancelled(Message):
        pass

    _pending_id: int = 0
    _pending_state: WorkItemState = WorkItemState.OPEN

    def compose(self) -> ComposeResult:
        yield Static("", classes="confirm-text", id="confirm-text")

    def show_confirmation(self, work_item_id: int, new_state: WorkItemState) -> None:
        self._pending_id = work_item_id
        self._pending_state = new_state
        try:
            label = self.query_one("#confirm-text", Static)
            label.update(
                f"Set [#5fafd7]#{work_item_id}[/] to "
                f"[bold]{new_state.display}[/]? "
                f"([#5a8a5a]y[/]es / [#b05050]n[/]o)"
            )
        except Exception:
            pass
        self.add_class("--visible")

    def hide(self) -> None:
        self.remove_class("--visible")

    def confirm(self) -> None:
        self.post_message(self.Confirmed(self._pending_id, self._pending_state))
        self.hide()

    def cancel(self) -> None:
        self.post_message(self.Cancelled())
        self.hide()

    @property
    def is_visible(self) -> bool:
        return self.has_class("--visible")
