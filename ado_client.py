"""Azure DevOps API client for the dashboard."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import Any

from azure.devops.connection import Connection
from azure.devops.v7_1.work_item_tracking import WorkItemTrackingClient
from azure.devops.v7_1.work_item_tracking.models import (
    JsonPatchOperation,
    Wiql,
)
from azure.devops.v7_1.work.models import TeamContext, TeamSettingsIteration
from msrest.authentication import BasicAuthentication

from config import get_active
from models import (
    DashboardData,
    EnablingSpec,
    Sprint,
    WorkItem,
    WorkItemState,
)

def _parse_date(val: Any) -> datetime | None:
    """Parse a date value from ADO fields (datetime obj or ISO string)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if hasattr(val, "isoformat"):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


DEFAULT_TAG = "WeeklyTarget"


def _cfg():
    return get_active()


def _get_az_token() -> str:
    """Get an Azure DevOps PAT from the Azure CLI."""
    import shutil
    import sys

    # On Windows, 'az' may not resolve without the .cmd extension
    az_cmd = "az"
    if sys.platform == "win32":
        az_cmd = shutil.which("az") or shutil.which("az.cmd") or "az.cmd"

    # Strip NuGet credential provider env vars that can cause az CLI
    # to attempt interactive auth dialogs (hangs in non-interactive contexts)
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("NUGET_CREDENTIALPROVIDER")}

    result = subprocess.run(
        [az_cmd, "account", "get-access-token", "--resource", "499b84ac-1321-427f-aa17-267ca6975798", "--query", "accessToken", "-o", "tsv"],
        capture_output=True,
        text=True,
        timeout=30,
        env=clean_env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Azure CLI auth failed. Run 'az login' first.\n{result.stderr}"
        )
    return result.stdout.strip()


def _get_connection() -> Connection:
    """Create an authenticated connection to Azure DevOps."""
    token = _get_az_token()
    credentials = BasicAuthentication("", token)
    return Connection(base_url=_cfg().org_url, creds=credentials)


def list_iterations(past: int = 5, future: int = 1) -> tuple[list[Sprint], int]:
    """Fetch sprints around the current one.

    Returns (sprints, current_index). The list is ordered chronologically and
    contains up to `past` previous sprints, the current sprint, and up to
    `future` upcoming sprints.
    """
    conn = _get_connection()
    work_client = conn.clients.get_work_client()
    team_context = TeamContext(project=_cfg().project, team=_cfg().team)
    all_iters: list[TeamSettingsIteration] = work_client.get_team_iterations(
        team_context=team_context,
    )
    if not all_iters:
        raise RuntimeError("No iterations found for team.")

    def to_sprint(it: TeamSettingsIteration) -> Sprint:
        start = finish = None
        if it.attributes:
            start = _parse_date(getattr(it.attributes, "start_date", None))
            finish = _parse_date(getattr(it.attributes, "finish_date", None))
        return Sprint(id=str(it.id), name=it.name, path=it.path,
                      start_date=start, finish_date=finish)

    def time_cat(it: TeamSettingsIteration) -> str:
        return (getattr(it.attributes, "time_frame", "") or "").lower() if it.attributes else ""

    # Find current sprint index in the full list.
    current_idx = next(
        (i for i, it in enumerate(all_iters) if time_cat(it) == "current"),
        None,
    )
    if current_idx is None:
        # Fall back to date-based detection.
        now = datetime.now()
        for i, it in enumerate(all_iters):
            s = to_sprint(it)
            if s.start_date and s.finish_date:
                start = s.start_date.replace(tzinfo=None)
                finish = s.finish_date.replace(tzinfo=None)
                if start <= now <= finish:
                    current_idx = i
                    break
    if current_idx is None:
        current_idx = len(all_iters) - 1

    lo = max(0, current_idx - past)
    hi = min(len(all_iters), current_idx + future + 1)
    window = [to_sprint(it) for it in all_iters[lo:hi]]
    return window, current_idx - lo


def get_current_sprint() -> Sprint:
    """Fetch the current sprint for the team."""
    conn = _get_connection()
    work_client = conn.clients.get_work_client()
    team_context = TeamContext(project=_cfg().project, team=_cfg().team)
    iterations: list[TeamSettingsIteration] = work_client.get_team_iterations(
        team_context=team_context,
        timeframe="current",
    )
    if not iterations:
        raise RuntimeError("No current sprint found for team.")

    it = iterations[0]
    start = None
    finish = None
    if it.attributes:
        attrs = it.attributes
        start_raw = getattr(attrs, "start_date", None)
        finish_raw = getattr(attrs, "finish_date", None)
        if hasattr(start_raw, "isoformat"):
            start = start_raw
        elif isinstance(start_raw, str):
            start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        if hasattr(finish_raw, "isoformat"):
            finish = finish_raw
        elif isinstance(finish_raw, str):
            finish = datetime.fromisoformat(finish_raw.replace("Z", "+00:00"))

    return Sprint(
        id=str(it.id),
        name=it.name,
        path=it.path,
        start_date=start,
        finish_date=finish,
    )


def fetch_work_items(sprint: Sprint, tag: str | None = DEFAULT_TAG) -> DashboardData:
    """Fetch all work items for the current sprint assigned to the user."""
    conn = _get_connection()
    wit_client: WorkItemTrackingClient = conn.clients.get_work_item_tracking_client()

    # Build WIQL query
    tag_clause = ""
    if tag:
        tag_clause = f"AND [System.Tags] CONTAINS '{tag}'"

    wiql_text = f"""
    SELECT [System.Id]
    FROM WorkItems
    WHERE [System.IterationPath] UNDER '{sprint.path}'
      AND [System.AssignedTo] = '{_cfg().user_email}'
      AND [System.WorkItemType] IN ('Enabling Specification', 'Task')
      AND [System.State] <> 'Removed'
      {tag_clause}
    ORDER BY [System.WorkItemType] DESC, [System.State]
    """

    team_ctx = TeamContext(project=_cfg().project, team=_cfg().team)
    wiql_result = wit_client.query_by_wiql(
        Wiql(query=wiql_text),
        team_context=team_ctx,
        top=200,
    )

    if not wiql_result.work_items:
        return DashboardData(sprint=sprint, last_refresh=datetime.now())

    ids = [wi.id for wi in wiql_result.work_items]

    # Batch fetch with relations (can't combine fields + expand)
    work_items_raw = wit_client.get_work_items(
        ids=ids,
        project=_cfg().project,
        expand="Relations",
    )

    # Parse into WorkItem objects
    items_by_id: dict[int, WorkItem] = {}
    for raw in work_items_raw:
        f = raw.fields
        tags_str = f.get("System.Tags", "") or ""
        tags = [t.strip() for t in tags_str.split(";") if t.strip()]

        child_ids = []
        if raw.relations:
            for rel in raw.relations:
                if rel.rel == "System.LinkTypes.Hierarchy-Forward":
                    # Extract ID from URL
                    child_id = int(rel.url.rstrip("/").split("/")[-1])
                    child_ids.append(child_id)

        item = WorkItem(
            id=raw.id,
            title=f.get("System.Title", ""),
            work_item_type=f.get("System.WorkItemType", ""),
            state=WorkItemState.from_str(f.get("System.State", "Open")),
            tags=tags,
            area_path=f.get("System.AreaPath", ""),
            iteration_path=f.get("System.IterationPath", ""),
            child_ids=child_ids,
            state_changed_date=_parse_date(f.get("Microsoft.VSTS.Common.StateChangeDate")),
        )
        items_by_id[item.id] = item

    # Resolve parent→child relationships
    # Build a map from spec ID → set of known child IDs
    spec_ids = {item.id for item in items_by_id.values() if item.is_enabling_spec}

    # Find tasks whose parent spec is NOT in our query results
    orphan_task_parent_ids: set[int] = set()
    task_to_parent: dict[int, int] = {}

    for raw in work_items_raw:
        if raw.fields.get("System.WorkItemType") == "Task" and raw.relations:
            for rel in raw.relations:
                if rel.rel == "System.LinkTypes.Hierarchy-Reverse":
                    parent_id = int(rel.url.rstrip("/").split("/")[-1])
                    task_to_parent[raw.id] = parent_id
                    if parent_id not in items_by_id:
                        orphan_task_parent_ids.add(parent_id)

    # Fetch orphan parents if needed
    if orphan_task_parent_ids:
        orphan_parents_raw = wit_client.get_work_items(
            ids=list(orphan_task_parent_ids),
            project=_cfg().project,
            fields=["System.Id", "System.Title", "System.WorkItemType", "System.State", "System.Tags", "System.AreaPath", "Microsoft.VSTS.Common.StateChangeDate"],
        )
        for raw in orphan_parents_raw:
            f = raw.fields
            tags_str = f.get("System.Tags", "") or ""
            tags = [t.strip() for t in tags_str.split(";") if t.strip()]
            item = WorkItem(
                id=raw.id,
                title=f.get("System.Title", ""),
                work_item_type=f.get("System.WorkItemType", ""),
                state=WorkItemState.from_str(f.get("System.State", "Open")),
                tags=tags,
                area_path=f.get("System.AreaPath", ""),
                child_ids=[],
                state_changed_date=_parse_date(f.get("Microsoft.VSTS.Common.StateChangeDate")),
            )
            items_by_id[item.id] = item

    # Collect ALL child IDs from every enabling spec's forward links
    all_spec_child_ids: set[int] = set()
    for item in items_by_id.values():
        if item.is_enabling_spec:
            all_spec_child_ids.update(item.child_ids)
    # Also include children pointed to by tasks' reverse links
    for tid, pid in task_to_parent.items():
        all_spec_child_ids.add(tid)

    # Find child IDs not already fetched (cross-sprint tasks)
    missing_child_ids = all_spec_child_ids - set(items_by_id.keys())
    if missing_child_ids:
        cross_sprint_raw = wit_client.get_work_items(
            ids=list(missing_child_ids),
            project=_cfg().project,
            expand="Relations",
        )
        for raw in cross_sprint_raw:
            f = raw.fields
            wtype = f.get("System.WorkItemType", "")
            if wtype != "Task":
                continue
            tags_str = f.get("System.Tags", "") or ""
            tags = [t.strip() for t in tags_str.split(";") if t.strip()]
            iter_path = f.get("System.IterationPath", "")
            state = WorkItemState.from_str(f.get("System.State", "Open"))

            # Determine sprint label from iteration path (last segment)
            cross_sprint_label = None
            if iter_path and iter_path != sprint.path:
                cross_sprint_label = iter_path.rsplit("\\", 1)[-1]

            item = WorkItem(
                id=raw.id,
                title=f.get("System.Title", ""),
                work_item_type=wtype,
                state=state,
                tags=tags,
                area_path=f.get("System.AreaPath", ""),
                iteration_path=iter_path,
                child_ids=[],
                completed_in_sprint=cross_sprint_label,
                state_changed_date=_parse_date(f.get("Microsoft.VSTS.Common.StateChangeDate")),
            )
            items_by_id[item.id] = item

            # Map parent from reverse link
            if raw.relations:
                for rel in raw.relations:
                    if rel.rel == "System.LinkTypes.Hierarchy-Reverse":
                        parent_id = int(rel.url.rstrip("/").split("/")[-1])
                        task_to_parent[raw.id] = parent_id

    # Build hierarchy
    enabling_specs: list[EnablingSpec] = []
    used_task_ids: set[int] = set()
    used_spec_ids: set[int] = set()

    # First: specs that are in our query results — attach children via
    # both the spec's forward-links AND tasks' reverse-links
    for item in list(items_by_id.values()):
        if not item.is_enabling_spec:
            continue
        tasks = []
        # Children from spec's forward relations
        child_candidates = set(item.child_ids)
        # Also pick up tasks that point back to this spec
        for tid, pid in task_to_parent.items():
            if pid == item.id:
                child_candidates.add(tid)
        for cid in child_candidates:
            if cid in items_by_id and items_by_id[cid].is_task:
                child = items_by_id[cid]
                child.parent_id = item.id
                tasks.append(child)
                used_task_ids.add(cid)
        enabling_specs.append(EnablingSpec(item=item, tasks=tasks))
        used_spec_ids.add(item.id)

    # Second: orphan parents (specs not assigned to user but their tasks are)
    for parent_id in orphan_task_parent_ids:
        if parent_id in items_by_id and parent_id not in used_spec_ids:
            parent = items_by_id[parent_id]
            tasks = []
            for tid, pid in task_to_parent.items():
                if pid == parent_id and tid in items_by_id and tid not in used_task_ids:
                    child = items_by_id[tid]
                    child.parent_id = parent_id
                    tasks.append(child)
                    used_task_ids.add(tid)
            if tasks:
                enabling_specs.append(EnablingSpec(item=parent, tasks=tasks))

    # Standalone tasks (no parent in result set)
    standalone = [
        item for item in items_by_id.values()
        if item.is_task and item.id not in used_task_ids
    ]

    return DashboardData(
        sprint=sprint,
        enabling_specs=enabling_specs,
        standalone_tasks=standalone,
        last_refresh=datetime.now(),
    )


def create_enabling_spec(title: str, iteration_path: str, area_path: str) -> int:
    """Create an Enabling Specification assigned to the current user.

    Uses the provided iteration and area paths, adds the 'Triaged' tag,
    and assigns to the configured user. Returns the new work item ID.
    """
    conn = _get_connection()
    wit_client: WorkItemTrackingClient = conn.clients.get_work_item_tracking_client()

    patch_doc = [
        JsonPatchOperation(op="add", path="/fields/System.Title", value=title),
        JsonPatchOperation(op="add", path="/fields/System.IterationPath", value=iteration_path),
        JsonPatchOperation(op="add", path="/fields/System.AreaPath", value=area_path),
        JsonPatchOperation(op="add", path="/fields/System.AssignedTo", value=_cfg().user_email),
        JsonPatchOperation(op="add", path="/fields/System.Tags", value="Triaged"),
    ]

    new_item = wit_client.create_work_item(
        document=patch_doc,
        project=_cfg().project,
        type="Enabling Specification",
    )
    return new_item.id


def create_child_task(parent_spec_id: int, title: str, iteration_path: str | None = None) -> int:
    """Create a Task as a child of an Enabling Specification.

    Copies assignee, area path, and tags from the parent. The iteration path
    is taken from the parent unless `iteration_path` is provided.
    Returns the new work item ID.
    """
    conn = _get_connection()
    wit_client: WorkItemTrackingClient = conn.clients.get_work_item_tracking_client()

    # Fetch parent spec details
    parent = wit_client.get_work_item(
        id=parent_spec_id,
        project=_cfg().project,
        fields=[
            "System.AssignedTo",
            "System.IterationPath",
            "System.AreaPath",
            "System.Tags",
        ],
    )
    pf = parent.fields

    patch_doc = [
        JsonPatchOperation(op="add", path="/fields/System.Title", value=title),
        JsonPatchOperation(op="add", path="/fields/System.WorkItemType", value="Task"),
        JsonPatchOperation(
            op="add",
            path="/fields/System.IterationPath",
            value=iteration_path or pf.get("System.IterationPath", ""),
        ),
        JsonPatchOperation(
            op="add",
            path="/fields/System.AreaPath",
            value=pf.get("System.AreaPath", ""),
        ),
    ]

    # Copy assignee if present
    assigned_to = pf.get("System.AssignedTo")
    if assigned_to:
        # assigned_to can be a dict with uniqueName or a string
        if isinstance(assigned_to, dict):
            email = assigned_to.get("uniqueName", assigned_to.get("displayName", ""))
        else:
            email = str(assigned_to)
        if email:
            patch_doc.append(
                JsonPatchOperation(op="add", path="/fields/System.AssignedTo", value=email)
            )

    # Copy tags if present
    tags = pf.get("System.Tags", "")
    if tags:
        patch_doc.append(
            JsonPatchOperation(op="add", path="/fields/System.Tags", value=tags)
        )

    # Add parent link
    patch_doc.append(
        JsonPatchOperation(
            op="add",
            path="/relations/-",
            value={
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"{_cfg().org_url}/{_cfg().project}/_apis/wit/workItems/{parent_spec_id}",
            },
        )
    )

    new_item = wit_client.create_work_item(
        document=patch_doc,
        project=_cfg().project,
        type="Task",
    )
    return new_item.id


def update_work_item_title(work_item_id: int, new_title: str) -> bool:
    """Update a work item's title in ADO. Returns True on success."""
    conn = _get_connection()
    wit_client = conn.clients.get_work_item_tracking_client()

    patch_doc = [
        JsonPatchOperation(
            op="replace",
            path="/fields/System.Title",
            value=new_title,
        )
    ]

    wit_client.update_work_item(
        document=patch_doc,
        id=work_item_id,
        project=_cfg().project,
    )
    return True


def update_work_item_tags(work_item_id: int, tags: list[str]) -> bool:
    """Update a work item's tags in ADO. Returns True on success."""
    conn = _get_connection()
    wit_client = conn.clients.get_work_item_tracking_client()

    patch_doc = [
        JsonPatchOperation(
            op="replace",
            path="/fields/System.Tags",
            value="; ".join(tags),
        )
    ]

    wit_client.update_work_item(
        document=patch_doc,
        id=work_item_id,
        project=_cfg().project,
    )
    return True


def update_work_item_iteration(work_item_id: int, iteration_path: str) -> bool:
    """Move a work item to a different iteration. Returns True on success."""
    conn = _get_connection()
    wit_client = conn.clients.get_work_item_tracking_client()

    patch_doc = [
        JsonPatchOperation(
            op="replace",
            path="/fields/System.IterationPath",
            value=iteration_path,
        )
    ]

    wit_client.update_work_item(
        document=patch_doc,
        id=work_item_id,
        project=_cfg().project,
    )
    return True


def update_work_item_state(work_item_id: int, new_state: WorkItemState) -> bool:
    """Update a work item's state in ADO. Returns True on success."""
    conn = _get_connection()
    wit_client = conn.clients.get_work_item_tracking_client()

    patch_doc = [
        JsonPatchOperation(
            op="replace",
            path="/fields/System.State",
            value=new_state.value,
        )
    ]

    wit_client.update_work_item(
        document=patch_doc,
        id=work_item_id,
        project=_cfg().project,
    )
    return True
