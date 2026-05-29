# ADO Sprint Dashboard

A keyboard-driven terminal dashboard for Azure DevOps that shows the work
items assigned to you in the current sprint, organized as a navigable
tree of **Enabling Specifications** and their child **Tasks**. You can
switch states, edit titles, create new tasks and specs, move items
between iterations, and jump to the web view — all without leaving the
terminal.

Built with [Textual](https://textual.textualize.io/).

## Requirements

- Python 3.10+
- [Azure CLI](https://learn.microsoft.com/cli/azure/) signed in via
  `az login` (the dashboard re-uses the cached token; no PATs are
  stored).

## Install

```
pip install -e .
```

This installs an `ado-dashboard` script. You can also run the app
directly with `python dashboard.py`.

## First Run

The very first time you launch the dashboard, a setup dialog asks for
four values:

| Field | Example |
|---|---|
| Organization | `contoso` (the segment after `dev.azure.com/`) |
| Project | `MyProject` |
| Team | `MyTeam` |
| Your work email | `you@example.com` |

These are written to `~/.ado-dashboard/config.json`. Delete that file to
re-run the setup.

## Usage

```
ado-dashboard [--interval SECONDS] [--tag TAG] [--no-tag] [--no-refresh]
```

- `--interval` — auto-refresh interval (default: 1800s / 30 min, min: 10s)
- `--tag` — tag filter (default: `WeeklyTarget`)
- `--no-tag` — disable tag filtering, show all sprint items
- `--no-refresh` — fetch once, no auto-refresh (still interactive)

## Keybindings

| Key | Action |
|---|---|
| `up` / `down` / `j` / `k` | Move selection |
| `enter` / `space` | Expand or collapse an enabling spec |
| `e` / `w` | Expand all / collapse all |
| `o` / `i` / `v` / `c` / `x` | Set state to Open / In Progress / Resolved / Closed / Blocked |
| `b` | Open the selected item in the browser |
| `y` | Copy the item URL to the clipboard |
| `t` | Edit the title of the selected item |
| `a` | Add a child task under the selected spec |
| `n` | Create a new Enabling Specification in the current iteration |
| `g` | Toggle the `WeeklyTarget` tag on the selected item |
| `f` | Toggle the tag filter (current tag ↔ All) |
| `s` | Pick a different iteration (previous 5, current, next) |
| `m` | Move the selected item to a different iteration |
| `/` | Filter by title |
| `r` | Refresh now |
| `q` | Quit |

When a spec is moved, child tasks that share the spec's old iteration
move with it. Tasks already pinned to a different iteration stay where
they are.

## Authentication

The dashboard does not store any credentials. At startup it shells out
to `az account get-access-token` with the Azure DevOps OAuth resource
ID. If you see `Azure CLI auth failed`, run `az login` and try again.

## Configuration File

```
~/.ado-dashboard/config.json
```

```json
{
  "organization": "contoso",
  "project": "MyProject",
  "team": "MyTeam",
  "user_email": "you@example.com"
}
```

You can edit this file by hand, or delete it and the dashboard will
prompt again on next launch.
