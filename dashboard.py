"""ADO Sprint Dashboard - Main Application."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.worker import get_current_worker
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.events import Key
from textual.command import CommandPalette
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

import webbrowser

from ado_client import create_child_task, create_enabling_spec, fetch_work_items, get_current_sprint, list_iterations, update_work_item_iteration, update_work_item_state, update_work_item_tags, update_work_item_title
from config import AppConfig, load_config, save_config, set_active
from models import DashboardData, Sprint, WorkItemState, ado_item_url
from widgets import ConfirmBar, DashboardHeader, StatusLine, WorkItemTree


class SearchBar(Container):
    DEFAULT_CSS = """
    SearchBar {
        dock: bottom;
        height: 3;
        display: none;
        padding: 0 1;
        background: #1e2a3a;
        border-top: solid #3a5070;
    }

    SearchBar.--visible {
        display: block;
    }

    SearchBar #search-label {
        width: 100%;
        height: 1;
        color: #8a9ab0;
    }

    SearchBar #search-input {
        width: 100%;
        height: 1;
        border: none;
        background: #253040;
        color: #e0e0e0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]/ Search[/]  [dim](Esc to close, Enter to keep filter)[/]", id="search-label")
        yield Input(placeholder="Type to filter by title...", id="search-input")

    def show(self) -> None:
        self.add_class("--visible")
        try:
            self.query_one("#search-input", Input).focus()
        except Exception:
            pass

    def hide(self) -> None:
        self.remove_class("--visible")
        try:
            inp = self.query_one("#search-input", Input)
            inp.value = ""
        except Exception:
            pass

    @property
    def is_visible(self) -> bool:
        return self.has_class("--visible")


class TitleInputScreen(ModalScreen[str | None]):
    """Centered modal dialog for entering/editing a title."""

    DEFAULT_CSS = """
    TitleInputScreen {
        align: center middle;
    }

    TitleInputScreen #dialog-box {
        width: 80%;
        max-width: 120;
        height: auto;
        max-height: 14;
        background: #1e2a3a;
        border: thick #3a5070;
        padding: 1 2;
    }

    TitleInputScreen #dialog-header {
        width: 100%;
        text-align: center;
        color: #e0e0e0;
        text-style: bold;
        margin-bottom: 1;
    }

    TitleInputScreen #dialog-input {
        width: 100%;
        border: tall #3a5070;
        background: #253040;
        color: #e0e0e0;
    }

    TitleInputScreen #dialog-hint {
        width: 100%;
        text-align: center;
        color: #6a7a8e;
        margin-top: 1;
    }

    TitleInputScreen #dialog-inherit-hint {
        width: 100%;
        text-align: center;
        color: #5a7a5a;
        margin-top: 0;
    }
    """

    def __init__(self, header_text: str, initial_value: str = "", inherit_hint: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._header_text = header_text
        self._initial_value = initial_value
        self._inherit_hint = inherit_hint

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            yield Static(self._header_text, id="dialog-header")
            yield Input(value=self._initial_value, id="dialog-input")
            yield Static("Enter = confirm  |  Esc = cancel", id="dialog-hint")
            if self._inherit_hint:
                yield Static(self._inherit_hint, id="dialog-inherit-hint")

    def on_mount(self) -> None:
        inp = self.query_one("#dialog-input", Input)
        inp.focus()
        # Move cursor to end
        inp.action_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        title = event.value.strip()
        self.dismiss(title if title else None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()


class SetupScreen(ModalScreen[AppConfig | None]):
    """First-run setup dialog that collects ADO connection details."""

    DEFAULT_CSS = """
    SetupScreen {
        align: center middle;
    }

    SetupScreen #setup-box {
        width: 80%;
        max-width: 100;
        height: 90%;
        max-height: 32;
        background: #1e2a3a;
        border: thick #3a5070;
        padding: 1 2;
        overflow-y: auto;
    }

    SetupScreen #setup-header {
        width: 100%;
        text-align: center;
        color: #e0e0e0;
        text-style: bold;
        margin-bottom: 1;
    }

    SetupScreen #setup-intro {
        width: 100%;
        color: #a0b0c0;
        margin-bottom: 1;
    }

    SetupScreen #setup-url-example {
        width: 100%;
        color: #8a9ab0;
        margin-bottom: 1;
    }

    SetupScreen .field-hint {
        width: 100%;
        color: #6a7a8e;
        margin-bottom: 0;
    }

    SetupScreen .field-label {
        width: 100%;
        color: #8a9ab0;
        margin-top: 1;
    }

    SetupScreen Input {
        width: 100%;
        border: tall #3a5070;
        background: #253040;
        color: #e0e0e0;
    }

    SetupScreen #setup-error {
        width: 100%;
        color: #e06060;
        margin-top: 1;
    }

    SetupScreen #setup-hint {
        width: 100%;
        text-align: center;
        color: #6a7a8e;
        margin-top: 1;
    }
    """

    def __init__(self, initial: AppConfig | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial = initial

    def compose(self) -> ComposeResult:
        i = self._initial
        with VerticalScroll(id="setup-box"):
            yield Static("[bold #88b8e0]Welcome — set up your ADO connection[/]", id="setup-header")
            yield Static(
                "Open your team's sprint backlog in the browser and copy the values "
                "from its URL. Saved to [#a3be8c]~/.ado-dashboard/config.json[/]. "
                "Press [bold #e6b800]Esc[/] to exit the setup.",
                id="setup-intro",
            )
            yield Static(
                "URL shape:  https://[#e6b800]{org}[/].visualstudio.com/"
                "[#a3be8c]{project}[/]/_sprints/backlog/[#88b8e0]{team}[/]/...\n"
                "       or:  https://dev.azure.com/[#e6b800]{org}[/]/"
                "[#a3be8c]{project}[/]/_sprints/backlog/[#88b8e0]{team}[/]/...",
                id="setup-url-example",
            )
            yield Static("Organization [dim](first URL segment, e.g. [#e6b800]contoso[/])[/]", classes="field-label")
            yield Input(value=(i.organization if i else ""), id="setup-org")
            yield Static("Project [dim](segment after the org, e.g. [#a3be8c]MyProject[/])[/]", classes="field-label")
            yield Input(value=(i.project if i else ""), id="setup-project")
            yield Static("Team [dim](segment after [#5fafd7]/_sprints/backlog/[/], e.g. [#88b8e0]MyTeam[/])[/]", classes="field-label")
            yield Input(value=(i.team if i else ""), id="setup-team")
            yield Static("Your work email [dim](the one you sign into ADO with)[/]", classes="field-label")
            yield Input(value=(i.user_email if i else ""), id="setup-email")
            yield Static("", id="setup-error")
            yield Static("Enter (on any field) = save  |  Esc = quit", id="setup-hint")

    def on_mount(self) -> None:
        self.query_one("#setup-org", Input).focus()

    def _values(self) -> dict[str, str]:
        return {
            "organization": self.query_one("#setup-org", Input).value.strip(),
            "project": self.query_one("#setup-project", Input).value.strip(),
            "team": self.query_one("#setup-team", Input).value.strip(),
            "user_email": self.query_one("#setup-email", Input).value.strip(),
        }

    def on_input_submitted(self, event: Input.Submitted) -> None:
        vals = self._values()
        missing = [k for k, v in vals.items() if not v]
        if missing:
            err = self.query_one("#setup-error", Static)
            err.update(f"[bold]Missing:[/] {', '.join(missing)}")
            # Focus the first missing field for convenience.
            field_id = {
                "organization": "#setup-org",
                "project": "#setup-project",
                "team": "#setup-team",
                "user_email": "#setup-email",
            }[missing[0]]
            self.query_one(field_id, Input).focus()
            return
        self.dismiss(AppConfig(**vals))

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()


class IterationPickerScreen(ModalScreen[Sprint | None]):
    """Modal dialog for picking an iteration from a small window of sprints."""

    DEFAULT_CSS = """
    IterationPickerScreen {
        align: center middle;
    }

    IterationPickerScreen #picker-box {
        width: 70%;
        max-width: 90;
        height: auto;
        max-height: 20;
        background: #1e2a3a;
        border: thick #3a5070;
        padding: 1 2;
    }

    IterationPickerScreen #picker-header {
        width: 100%;
        text-align: center;
        color: #e0e0e0;
        text-style: bold;
        margin-bottom: 1;
    }

    IterationPickerScreen #picker-list {
        width: 100%;
        height: auto;
        max-height: 12;
        background: #253040;
        border: tall #3a5070;
    }

    IterationPickerScreen #picker-hint {
        width: 100%;
        text-align: center;
        color: #6a7a8e;
        margin-top: 1;
    }
    """

    def __init__(self, sprints: list[Sprint], current_index: int, active_id: str | None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._sprints = sprints
        self._current_index = current_index
        self._active_id = active_id

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Static("[bold #88b8e0]Pick Iteration[/]", id="picker-header")
            options: list[Option] = []
            for i, s in enumerate(self._sprints):
                marker = ""
                if i == self._current_index:
                    marker = " [#a3be8c](current)[/]"
                elif i == self._current_index + 1:
                    marker = " [#c8a855](next)[/]"
                dates = f"  [dim]{s.date_range}[/]" if s.date_range else ""
                active = "[#5fafd7]▸[/] " if s.id == self._active_id else "  "
                options.append(Option(f"{active}{s.name}{marker}{dates}", id=s.id))
            yield OptionList(*options, id="picker-list")
            yield Static("Enter = select  |  Esc = cancel", id="picker-hint")

    def on_mount(self) -> None:
        ol = self.query_one("#picker-list", OptionList)
        ol.focus()
        # Highlight the currently active sprint, falling back to current.
        target_id = self._active_id
        idx = None
        if target_id:
            for i, s in enumerate(self._sprints):
                if s.id == target_id:
                    idx = i
                    break
        if idx is None:
            idx = self._current_index
        if 0 <= idx < len(self._sprints):
            ol.highlighted = idx

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        selected_id = event.option.id
        for s in self._sprints:
            if s.id == selected_id:
                self.dismiss(s)
                return
        self.dismiss(None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()


class ConfirmDialogScreen(ModalScreen[bool]):
    """Centered modal that asks for a y/n confirmation."""

    DEFAULT_CSS = """
    ConfirmDialogScreen {
        align: center middle;
    }

    ConfirmDialogScreen #dialog-box {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 18;
        background: #1e2a3a;
        border: thick #3a5070;
        padding: 1 2;
    }

    ConfirmDialogScreen #dialog-header {
        width: 100%;
        text-align: center;
        color: #e0e0e0;
        text-style: bold;
        margin-bottom: 1;
    }

    ConfirmDialogScreen #dialog-body {
        width: 100%;
        height: auto;
        color: #c0c8d0;
    }

    ConfirmDialogScreen #dialog-hint {
        width: 100%;
        text-align: center;
        color: #6a7a8e;
        margin-top: 1;
    }
    """

    def __init__(self, header_text: str, body_text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._header_text = header_text
        self._body_text = body_text

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            yield Static(self._header_text, id="dialog-header")
            yield Static(self._body_text, id="dialog-body")
            yield Static("Y = confirm  |  N / Esc = cancel", id="dialog-hint")

    def on_key(self, event: Key) -> None:
        if event.key == "y":
            self.dismiss(True)
            event.prevent_default()
            event.stop()
        elif event.key in ("n", "escape"):
            self.dismiss(False)
            event.prevent_default()
            event.stop()


class AdoDashboard(App):
    """ADO Sprint Dashboard - Terminal UI."""

    TITLE = "Tarik's Work Dashboard"
    CSS_PATH = "dashboard.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "expand_all", "Expand All"),
        Binding("w", "collapse_all", "Collapse"),
        Binding("o", "set_open", "Reopen"),
        Binding("i", "set_in_progress", "Start"),
        Binding("v", "set_resolved", "Resolve"),
        Binding("c", "set_closed", "Close"),
        Binding("x", "set_blocked", "Block"),
        Binding("b", "open_browser", "Browse"),
        Binding("y", "copy_link", "Copy Link"),
        Binding("slash", "search", "Search"),
        Binding("a", "add_task", "Add Task"),
        Binding("n", "add_spec", "New Spec"),
        Binding("t", "edit_title", "Edit Title"),
        Binding("g", "toggle_weekly_target", "Toggle WT"),
        Binding("f", "toggle_tag_filter", "Filter"),
        Binding("s", "pick_iteration", "Iteration"),
        Binding("m", "move_iteration", "Move"),
    ]

    # Map binding keys to friendly display names for command palette
    _KEY_DISPLAY = {
        "slash": "/",
    }

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        for binding in self.BINDINGS:
            action = binding.action
            description = binding.description
            key = binding.key
            display_key = self._KEY_DISPLAY.get(key, key)
            yield SystemCommand(
                f"{description} ({display_key})",
                f"Key: {display_key}",
                lambda a=action: self.run_action(a),
            )

    def __init__(
        self,
        interval: int = 1800,
        tag: str | None = "WeeklyTarget",
        no_refresh: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._interval = interval
        self._tag = tag
        self._original_tag = tag  # remember startup tag for toggling
        self._no_refresh = no_refresh
        self._sprint: Sprint | None = None
        self._data: DashboardData | None = None
        self._refresh_timer_handle: asyncio.TimerHandle | None = None
        self._countdown_task: asyncio.Task | None = None
        self._next_refresh_at: datetime | None = None
        self._confirming = False

    def compose(self) -> ComposeResult:
        yield DashboardHeader()
        yield StatusLine()
        yield WorkItemTree()
        yield ConfirmBar()
        yield SearchBar()
        yield Footer()

    def on_mount(self) -> None:
        header = self.query_one(DashboardHeader)
        header.tag_filter = self._tag or "All"
        tree = self.query_one(WorkItemTree)
        tree.set_show_spec_tags(self._tag is None)
        tree.set_loading()

        cfg = load_config()
        if cfg is None:
            self.push_screen(SetupScreen(), callback=self._on_setup_done)
        else:
            set_active(cfg)
            self.do_refresh()

    def _on_setup_done(self, cfg: AppConfig | None) -> None:
        if cfg is None:
            self.exit()
            return
        try:
            save_config(cfg)
        except Exception as e:
            self.notify(f"Failed to save config: {e}", severity="error", timeout=8)
            self.exit()
            return
        set_active(cfg)
        self.notify("Configuration saved", timeout=3)
        self.do_refresh()

    @work(thread=True, exclusive=True, group="refresh")
    def do_refresh(self) -> None:
        """Fetch data from ADO in a background thread."""
        self.call_from_thread(self.query_one(WorkItemTree).set_loading)
        self.call_from_thread(self._set_status_loading, True)
        try:
            if not self._sprint:
                self._sprint = get_current_sprint()
            data = fetch_work_items(self._sprint, tag=self._tag)
            if get_current_worker().is_cancelled:
                return
            self.call_from_thread(self._apply_data, data)
        except Exception as e:
            if get_current_worker().is_cancelled:
                return
            self.call_from_thread(self._show_error, str(e))

    def _set_status_loading(self, loading: bool) -> None:
        try:
            self.query_one(StatusLine).loading = loading
        except Exception:
            pass

    def _apply_data(self, data: DashboardData) -> None:
        """Apply fetched data to the UI (runs on main thread)."""
        self._data = data
        self._set_status_loading(False)

        # Update header
        header = self.query_one(DashboardHeader)
        header.sprint_name = data.sprint.name
        header.sprint_dates = data.sprint.date_range
        header.last_refresh = (
            data.last_refresh.strftime("%H:%M:%S") if data.last_refresh else "Never"
        )

        # Update status line
        self._update_status_line(data)

        # Update tree
        tree = self.query_one(WorkItemTree)
        tree.update_data(data)

        # Schedule next refresh
        self._schedule_refresh()

    def _show_error(self, message: str) -> None:
        """Show error notification."""
        self.query_one(WorkItemTree).set_loading(False)
        self._set_status_loading(False)
        self.notify(
            f"Error: {message}",
            severity="error",
            timeout=10,
        )
        # Still schedule next refresh on error
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        """Schedule the next auto-refresh."""
        if self._no_refresh:
            header = self.query_one(DashboardHeader)
            header.next_refresh = "disabled"
            return

        self._next_refresh_at = datetime.now()
        # Cancel existing countdown
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self._countdown_task = asyncio.ensure_future(self._countdown_loop())

    async def _countdown_loop(self) -> None:
        """Update the countdown timer and trigger refresh."""
        header = self.query_one(DashboardHeader)
        remaining = self._interval
        while remaining > 0:
            mins, secs = divmod(remaining, 60)
            if mins > 0:
                header.next_refresh = f"{mins}m {secs:02d}s"
            else:
                header.next_refresh = f"{secs}s"
            await asyncio.sleep(1)
            remaining -= 1
        header.next_refresh = "refreshing..."
        self.do_refresh()

    def action_quit(self) -> None:
        """Cancel background tasks and exit immediately."""
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self.workers.cancel_all()
        self.exit()

    # ── Key bindings ────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        """Handle keys when confirm bar or search bar is active."""
        confirm = self.query_one(ConfirmBar)
        search = self.query_one(SearchBar)

        if confirm.is_visible:
            if event.key == "y":
                confirm.confirm()
                event.prevent_default()
                event.stop()
            elif event.key in ("n", "escape"):
                confirm.cancel()
                self._confirming = False
                event.prevent_default()
                event.stop()
            else:
                event.prevent_default()
                event.stop()
            return

        if search.is_visible:
            tree = self.query_one(WorkItemTree)
            if event.key == "escape":
                search.hide()
                tree.clear_filter()
                tree.focus()
                event.prevent_default()
                event.stop()
            elif event.key in ("up", "down"):
                # Navigate the tree while searching
                if event.key == "up":
                    tree.action_cursor_up()
                else:
                    tree.action_cursor_down()
                event.prevent_default()
                event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            tree = self.query_one(WorkItemTree)
            tree.set_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in search bar — keep filter, focus tree."""
        if event.input.id == "search-input":
            search = self.query_one(SearchBar)
            search.hide()
            tree = self.query_one(WorkItemTree)
            tree.focus()

    def action_refresh(self) -> None:
        if self._confirming:
            return
        self.notify("Refreshing...", timeout=2)
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self.do_refresh()

    def action_expand_all(self) -> None:
        if self._confirming:
            return
        self.query_one(WorkItemTree).expand_all()

    def action_collapse_all(self) -> None:
        if self._confirming:
            return
        self.query_one(WorkItemTree).collapse_all()

    def action_open_browser(self) -> None:
        if self._confirming:
            return
        tree = self.query_one(WorkItemTree)
        wid = tree.get_selected_work_item_id()
        if wid is not None:
            url = ado_item_url(wid)
            webbrowser.open(url)
            self.notify(f"Opened #{wid} in browser", timeout=2)

    def action_copy_link(self) -> None:
        if self._confirming:
            return
        tree = self.query_one(WorkItemTree)
        wid = tree.get_selected_work_item_id()
        if wid is not None:
            url = ado_item_url(wid)
            subprocess.run(
                ["clip.exe"],
                input=url.encode("utf-16le"),
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.notify(f"Copied link for #{wid}", timeout=2)

    def action_search(self) -> None:
        if self._confirming:
            return
        search = self.query_one(SearchBar)
        if search.is_visible:
            search.hide()
            self.query_one(WorkItemTree).clear_filter()
            self.query_one(WorkItemTree).focus()
        else:
            search.show()

    def action_command_palette(self) -> None:
        """Toggle the command palette instead of only opening it."""
        # If a CommandPalette screen is already on the stack, dismiss it
        for screen in reversed(self.screen_stack):
            if isinstance(screen, CommandPalette):
                screen.dismiss()
                return
        # Otherwise open it via the default behavior
        super().action_command_palette()

    def action_pick_iteration(self) -> None:
        if self._confirming:
            return
        self.notify("Loading iterations...", timeout=2)
        self._do_load_iterations()

    @work(thread=True, group="load-iterations")
    def _do_load_iterations(self) -> None:
        try:
            sprints, current_index = list_iterations(past=5, future=1)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to load iterations: {e}",
                severity="error",
                timeout=8,
            )
            return
        active_id = self._sprint.id if self._sprint else None
        self.call_from_thread(self._show_iteration_picker, sprints, current_index, active_id)

    def _show_iteration_picker(self, sprints: list[Sprint], current_index: int, active_id: str | None) -> None:
        self.push_screen(
            IterationPickerScreen(sprints, current_index, active_id),
            callback=self._on_iteration_picked,
        )

    def _on_iteration_picked(self, sprint: Sprint | None) -> None:
        if sprint is None:
            return
        if self._sprint and sprint.id == self._sprint.id:
            self.notify(f"Already on {sprint.name}", timeout=2)
            return
        self._sprint = sprint
        self.notify(f"Switched to {sprint.name}", timeout=3)
        self.query_one(WorkItemTree).set_loading()
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self.do_refresh()

    def _find_item_context(self, wid: int):
        """Return (item, child_tasks_or_none) for the given id, or (None, None)."""
        if not self._data:
            return None, None
        for es in self._data.enabling_specs:
            if es.item.id == wid:
                return es.item, es.tasks
            for t in es.tasks:
                if t.id == wid:
                    return t, None
        for t in self._data.standalone_tasks:
            if t.id == wid:
                return t, None
        return None, None

    def action_move_iteration(self) -> None:
        if self._confirming:
            return
        tree = self.query_one(WorkItemTree)
        wid = tree.get_selected_work_item_id()
        if wid is None:
            self.notify("Select an item to move", timeout=3)
            return
        item, _ = self._find_item_context(wid)
        if item is None:
            return
        self.notify("Loading iterations...", timeout=2)
        self._do_load_iterations_for_move(wid)

    @work(thread=True, group="load-iterations")
    def _do_load_iterations_for_move(self, wid: int) -> None:
        try:
            sprints, current_index = list_iterations(past=5, future=1)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to load iterations: {e}",
                severity="error",
                timeout=8,
            )
            return
        item, _ = self._find_item_context(wid)
        active_id = None
        if item:
            for s in sprints:
                if s.path == item.iteration_path:
                    active_id = s.id
                    break
        self.call_from_thread(self._show_move_picker, wid, sprints, current_index, active_id)

    def _show_move_picker(self, wid: int, sprints: list[Sprint], current_index: int, active_id: str | None) -> None:
        self.push_screen(
            IterationPickerScreen(sprints, current_index, active_id),
            callback=lambda target: self._on_move_target_picked(wid, target),
        )

    def _on_move_target_picked(self, wid: int, target: Sprint | None) -> None:
        if target is None:
            return
        item, child_tasks = self._find_item_context(wid)
        if item is None:
            return
        if item.iteration_path == target.path:
            self.notify(f"#{wid} is already in {target.name}", timeout=3)
            return

        # Determine cascade: only children whose iteration matches the spec's current one.
        cascade: list[int] = []
        stayed = 0
        if child_tasks is not None:
            for t in child_tasks:
                if t.iteration_path == item.iteration_path:
                    cascade.append(t.id)
                else:
                    stayed += 1

        is_spec = item.is_enabling_spec
        kind = "Enabling Spec" if is_spec else "Task"
        header = f"[bold #c8a855]Move {kind}[/]"
        body_lines = [
            f"Move [#5fafd7]#{wid}[/] [bold]{item.title}[/]",
            f"to [#a3be8c]{target.name}[/]?",
        ]
        if is_spec:
            body_lines.append("")
            if cascade:
                body_lines.append(
                    f"[#a3be8c]+{len(cascade)}[/] child task(s) in the same iteration will move too."
                )
            if stayed:
                body_lines.append(
                    f"[dim]{stayed} child task(s) in a different iteration will stay.[/]"
                )
            if not cascade and not stayed:
                body_lines.append("[dim]No child tasks.[/]")
        body = "\n".join(body_lines)

        self.push_screen(
            ConfirmDialogScreen(header, body),
            callback=lambda ok: self._on_move_confirmed(wid, target, cascade, ok),
        )

    def _on_move_confirmed(self, wid: int, target: Sprint, cascade: list[int], ok: bool) -> None:
        if not ok:
            return
        total = 1 + len(cascade)
        self.notify(f"Moving {total} item(s) to {target.name}...", timeout=3)
        self._do_move_iteration(wid, target.path, cascade)

    @work(thread=True, group="move-iteration")
    def _do_move_iteration(self, wid: int, new_path: str, cascade: list[int]) -> None:
        try:
            update_work_item_iteration(wid, new_path)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to move #{wid}: {e}",
                severity="error",
                timeout=8,
            )
            return

        failures: list[tuple[int, str]] = []
        for cid in cascade:
            try:
                update_work_item_iteration(cid, new_path)
            except Exception as e:
                failures.append((cid, str(e)))

        if failures:
            failed_ids = ", ".join(f"#{i}" for i, _ in failures)
            self.call_from_thread(
                self.notify,
                f"Moved #{wid} but failed for: {failed_ids}",
                severity="error",
                timeout=10,
            )
        else:
            moved = 1 + len(cascade)
            self.call_from_thread(
                self.notify,
                f"Moved {moved} item(s)",
                timeout=3,
            )
        self.call_from_thread(self.do_refresh)

    def action_toggle_tag_filter(self) -> None:
        if self._confirming:
            return
        if self._tag is not None:
            # Currently filtered → show all
            self._tag = None
        else:
            # Currently showing all → restore original filter
            self._tag = self._original_tag
        header = self.query_one(DashboardHeader)
        header.tag_filter = self._tag or "All"
        self.query_one(WorkItemTree).set_show_spec_tags(self._tag is None)
        self.notify(f"Filter: {self._tag or 'All'}", timeout=2)
        if self._countdown_task and not self._countdown_task.done():
            self._countdown_task.cancel()
        self.do_refresh()

    def action_toggle_weekly_target(self) -> None:
        if self._confirming:
            return
        tree = self.query_one(WorkItemTree)
        wid = tree.get_selected_work_item_id()
        if wid is None or not self._data:
            return
        # Find the item in data
        item = None
        for es in self._data.enabling_specs:
            if es.item.id == wid:
                item = es.item
                break
            for t in es.tasks:
                if t.id == wid:
                    item = t
                    break
            if item:
                break
        if not item:
            for t in self._data.standalone_tasks:
                if t.id == wid:
                    item = t
                    break
        if not item:
            return
        # Toggle the tag
        has_wt = "WeeklyTarget" in item.tags
        if has_wt:
            new_tags = [t for t in item.tags if t != "WeeklyTarget"]
            label = "Removed WT"
        else:
            new_tags = item.tags + ["WeeklyTarget"]
            label = "Added WT"
        # Optimistic update
        item.tags = new_tags
        tree._rebuild()
        self.notify(f"#{wid}: {label}", timeout=2)
        self._do_tag_update(wid, new_tags, item)

    @work(thread=True, group="tag-update")
    def _do_tag_update(self, wid: int, new_tags: list[str], item) -> None:
        try:
            update_work_item_tags(wid, new_tags)
        except Exception as e:
            # Revert on failure
            if "WeeklyTarget" in new_tags:
                item.tags = [t for t in new_tags if t != "WeeklyTarget"]
            else:
                item.tags = new_tags + ["WeeklyTarget"]
            self.call_from_thread(self.query_one(WorkItemTree)._rebuild)
            self.call_from_thread(
                self.notify,
                f"Failed to update tags for #{wid}: {e}",
                severity="error",
                timeout=8,
            )

    def action_add_task(self) -> None:
        if self._confirming:
            return
        tree = self.query_one(WorkItemTree)
        parent_id = tree.get_parent_spec_id()
        if parent_id is None:
            self.notify("Select an enabling spec or one of its tasks first", timeout=3)
            return
        # Get parent title for display
        parent_title = ""
        if self._data:
            for es in self._data.enabling_specs:
                if es.item.id == parent_id:
                    parent_title = es.item.title
                    break
        header = f"[bold #5a8a5a]Add Task[/] under [#5fafd7]#{parent_id}[/] {parent_title}"
        inherit_hint = "Assignee, tags, and iteration will be copied from parent"
        self.push_screen(
            TitleInputScreen(header, inherit_hint=inherit_hint),
            callback=lambda result: self._on_add_task_result(parent_id, result),
        )

    def _on_add_task_result(self, parent_id: int, title: str | None) -> None:
        if title:
            self.notify(f"Creating task under #{parent_id}...", timeout=3)
            self._do_create_task(parent_id, title)

    @work(thread=True, group="create-task")
    def _do_create_task(self, parent_id: int, title: str) -> None:
        """Create a child task via API in background, then refresh."""
        try:
            iteration_path = self._sprint.path if self._sprint else None
            new_id = create_child_task(parent_id, title, iteration_path=iteration_path)
            self.call_from_thread(
                self.notify,
                f"Created task #{new_id}: {title}",
                severity="information",
                timeout=5,
            )
            # Refresh to show the new task
            self.call_from_thread(self.do_refresh)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to create task: {e}",
                severity="error",
                timeout=8,
            )

    def action_add_spec(self) -> None:
        if self._confirming:
            return
        if not self._sprint:
            self.notify("Sprint not loaded yet", timeout=3)
            return
        # Determine area path from the first enabling spec in current data
        area_path = ""
        if self._data:
            for es in self._data.enabling_specs:
                if es.item.area_path:
                    area_path = es.item.area_path
                    break
        if not area_path:
            self.notify("No existing enabling spec to derive area path from", timeout=3)
            return
        header = "[bold #7a6f9a]New Enabling Spec[/]  [dim](Triaged, assigned to you)[/]"
        self.push_screen(
            TitleInputScreen(header),
            callback=lambda result: self._on_add_spec_result(result, area_path),
        )

    def _on_add_spec_result(self, title: str | None, area_path: str) -> None:
        if title:
            self.notify("Creating enabling spec...", timeout=3)
            self._do_create_spec(title, area_path)

    @work(thread=True, group="create-spec")
    def _do_create_spec(self, title: str, area_path: str) -> None:
        try:
            new_id = create_enabling_spec(
                title=title,
                iteration_path=self._sprint.path,
                area_path=area_path,
            )
            self.call_from_thread(
                self.notify,
                f"Created ES #{new_id}: {title}",
                severity="information",
                timeout=5,
            )
            self.call_from_thread(self.do_refresh)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                f"Failed to create enabling spec: {e}",
                severity="error",
                timeout=8,
            )

    def action_edit_title(self) -> None:
        if self._confirming:
            return
        tree = self.query_one(WorkItemTree)
        wid = tree.get_selected_work_item_id()
        current_title = tree.get_selected_title()
        if wid is None or current_title is None:
            return
        # Build header with parent spec context for child tasks
        header = f"[bold #c8a855]Edit Title[/] for [#5fafd7]#{wid}[/]"
        parent_id = tree.get_parent_spec_id()
        if parent_id is not None and parent_id != wid and self._data:
            for es in self._data.enabling_specs:
                if es.item.id == parent_id:
                    header += f"\n[dim]under [#5fafd7]#{parent_id}[/] {es.item.title}[/]"
                    break
        self.push_screen(
            TitleInputScreen(header, initial_value=current_title),
            callback=lambda result: self._on_edit_title_result(wid, current_title, result),
        )

    def _on_edit_title_result(self, wid: int, old_title: str, new_title: str | None) -> None:
        if new_title and new_title != old_title:
            # Optimistic update
            tree = self.query_one(WorkItemTree)
            tree.update_item_title(wid, new_title)
            self._do_title_update(wid, new_title, old_title)

    @work(thread=True, group="title-update")
    def _do_title_update(self, wid: int, new_title: str, old_title: str) -> None:
        """Update work item title via API in background."""
        try:
            update_work_item_title(wid, new_title)
            self.call_from_thread(
                self.notify,
                f"#{wid} title updated",
                severity="information",
                timeout=3,
            )
        except Exception as e:
            # Revert on failure
            self.call_from_thread(
                self.query_one(WorkItemTree).update_item_title,
                wid,
                old_title,
            )
            self.call_from_thread(
                self.notify,
                f"Failed to update title for #{wid}: {e}",
                severity="error",
                timeout=8,
            )

    def _request_state_change(self, new_state: WorkItemState) -> None:
        """Initiate a state change with confirmation."""
        tree = self.query_one(WorkItemTree)
        wid = tree.get_selected_work_item_id()
        current = tree.get_selected_state()
        if wid is None or current is None:
            return
        if current == new_state:
            self.notify(f"#{wid} is already {new_state.display}", timeout=3)
            return
        self._confirming = True
        confirm = self.query_one(ConfirmBar)
        confirm.show_confirmation(wid, new_state)

    def action_set_open(self) -> None:
        if not self._confirming:
            self._request_state_change(WorkItemState.OPEN)

    def action_set_in_progress(self) -> None:
        if not self._confirming:
            self._request_state_change(WorkItemState.IN_PROGRESS)

    def action_set_resolved(self) -> None:
        if not self._confirming:
            self._request_state_change(WorkItemState.RESOLVED)

    def action_set_closed(self) -> None:
        if not self._confirming:
            self._request_state_change(WorkItemState.CLOSED)

    def action_set_blocked(self) -> None:
        if not self._confirming:
            self._request_state_change(WorkItemState.BLOCKED)

    # ── Confirm bar messages ────────────────────────────────────

    def on_confirm_bar_confirmed(self, event: ConfirmBar.Confirmed) -> None:
        """User confirmed a status change."""
        self._confirming = False
        tree = self.query_one(WorkItemTree)
        old_state = tree.get_selected_state()

        # Optimistic update
        tree.update_item_state(event.work_item_id, event.new_state)
        self._update_status_line()

        # Fire API call in background
        self._do_state_update(event.work_item_id, event.new_state, old_state)

        # Re-focus tree
        tree.focus()

    def on_confirm_bar_cancelled(self, event: ConfirmBar.Cancelled) -> None:
        self._confirming = False
        self.query_one(WorkItemTree).focus()

    @work(thread=True, group="state-update")
    def _do_state_update(
        self,
        work_item_id: int,
        new_state: WorkItemState,
        old_state: WorkItemState | None,
    ) -> None:
        """Update work item state via API in background."""
        try:
            update_work_item_state(work_item_id, new_state)
            self.call_from_thread(
                self.notify,
                f"#{work_item_id} → {new_state.display}",
                severity="information",
                timeout=3,
            )
        except Exception as e:
            # Revert on failure
            if old_state:
                self.call_from_thread(
                    self.query_one(WorkItemTree).update_item_state,
                    work_item_id,
                    old_state,
                )
                self.call_from_thread(self._update_status_line)
            self.call_from_thread(
                self.notify,
                f"Failed to update #{work_item_id}: {e}",
                severity="error",
                timeout=8,
            )

    def _update_status_line(self, data: DashboardData | None = None) -> None:
        """Update the status line bar from data."""
        data = data or self._data
        if not data:
            return
        sl = self.query_one(StatusLine)
        sl.total = data.total_count
        sl.open_count = data.open_count
        sl.in_progress = data.in_progress_count
        sl.blocked_count = data.count_by_state(WorkItemState.BLOCKED)
        sl.done_count = data.resolved_count + data.closed_count


def main():
    parser = argparse.ArgumentParser(description="ADO Sprint Dashboard")
    parser.add_argument(
        "--interval",
        type=int,
        default=1800,
        help="Refresh interval in seconds (default: 1800, min: 10)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="WeeklyTarget",
        help="Tag filter (default: WeeklyTarget)",
    )
    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Disable tag filtering, show all sprint items",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Fetch once, still interactive but no auto-refresh",
    )

    args = parser.parse_args()

    interval = max(args.interval, 10)
    tag = None if args.no_tag else args.tag

    app = AdoDashboard(
        interval=interval,
        tag=tag,
        no_refresh=args.no_refresh,
    )
    app.run()


if __name__ == "__main__":
    main()
