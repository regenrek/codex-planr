#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


STATUS_FILE = Path(".planr/status/current.json")
PLANS_DIR = Path(".planr/plans")
VALID_SCOPE_STATUSES = {"pending", "in_progress", "completed", "blocked", "cancelled"}
VALID_CHECKLIST_STATUSES = VALID_SCOPE_STATUSES
VALID_BLOCKER_STATUSES = {"blocked", "unverified"}
VALID_VERIFICATION_STATUSES = {"passed", "failed", "blocked", "not_run"}
OPEN_SCOPE_STATUSES = {"pending", "in_progress", "blocked"}
NON_PASSED_VERIFICATION_STATUSES = VALID_VERIFICATION_STATUSES - {"passed"}


class CliError(RuntimeError):
    pass


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = []
    previous_was_sep = False
    for ch in normalized.lower():
        if ch.isalnum():
            cleaned.append(ch)
            previous_was_sep = False
            continue
        if not previous_was_sep:
            cleaned.append("_")
            previous_was_sep = True
    slug = "".join(cleaned).strip("_")
    return slug or "plan"


def title_hash(title: str) -> str:
    normalized = " ".join(title.strip().split()).lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]


def resolve_repo_root(repo_root: str | None) -> Path:
    if repo_root:
        root = Path(repo_root).expanduser().resolve()
        if not root.exists():
            raise CliError(f"Repo root does not exist: {root}")
        if not (root / ".planr").exists():
            raise CliError(f"Repo root does not contain `.planr/`: {root}")
        return root

    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".planr").exists():
            return candidate
    raise CliError("Could not find repo root containing `.planr/` from the current working directory.")


def ensure_relative_to_root(root: Path, raw_path: str) -> str:
    candidate = Path(raw_path).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise CliError(f"Path must stay inside the repo root: {raw_path}") from exc


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CliError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid JSON in {path}: {exc}") from exc


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def normalize_unique_paths(root: Path, values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    normalized = {ensure_relative_to_root(root, value) for value in values}
    return sorted(normalized)


def get_status_path(root: Path) -> Path:
    return root / STATUS_FILE


def load_status(root: Path) -> dict[str, Any]:
    return read_json(get_status_path(root))


def save_status(root: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = utc_timestamp()
    write_json(get_status_path(root), data)


def scopes(data: dict[str, Any]) -> list[dict[str, Any]]:
    scope_list = data.get("scopes")
    if not isinstance(scope_list, list):
        raise CliError("`.planr/status/current.json` is missing a valid `scopes` array.")
    return scope_list


def require_list_field(parent: dict[str, Any], key: str, owner: str) -> list[dict[str, Any]]:
    items = parent.setdefault(key, [])
    if not isinstance(items, list):
        raise CliError(f"`{owner}.{key}` must be a list in `.planr/status/current.json`.")
    return items


def get_list_field(parent: dict[str, Any], key: str, owner: str) -> list[Any]:
    items = parent.get(key, [])
    if items is None:
        return []
    if not isinstance(items, list):
        raise CliError(f"`{owner}.{key}` must be a list in `.planr/status/current.json`.")
    return items


def get_object_list(parent: dict[str, Any], key: str, owner: str) -> list[dict[str, Any]]:
    items = get_list_field(parent, key, owner)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise CliError(f"`{owner}.{key}[{index}]` must be an object in `.planr/status/current.json`.")
    return items  # type: ignore[return-value]


def require_valid_status(value: Any, valid: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in valid:
        raise CliError(f"{label} must be one of: {', '.join(sorted(valid))}")
    return value


def find_scope(data: dict[str, Any], scope_id: str) -> dict[str, Any] | None:
    for scope in scopes(data):
        if scope.get("id") == scope_id:
            return scope
    return None


def require_scope(data: dict[str, Any], scope_id: str) -> dict[str, Any]:
    scope = find_scope(data, scope_id)
    if scope is None:
        raise CliError(f"Scope not found: {scope_id}")
    return scope


def find_item_index(items: list[dict[str, Any]], item_id: str) -> int | None:
    for index, item in enumerate(items):
        if item.get("id") == item_id:
            return index
    return None


def upsert_item(
    items: list[dict[str, Any]],
    item_id: str,
    *,
    before_id: str | None = None,
    after_id: str | None = None,
) -> dict[str, Any]:
    if before_id == item_id or after_id == item_id:
        raise CliError("An item cannot be positioned relative to itself.")

    existing_index = find_item_index(items, item_id)
    if existing_index is not None:
        item = items.pop(existing_index)
    else:
        item = {"id": item_id}

    if before_id is not None:
        anchor_index = find_item_index(items, before_id)
        if anchor_index is None:
            raise CliError(f"Anchor item not found: {before_id}")
        items.insert(anchor_index, item)
        return item

    if after_id is not None:
        anchor_index = find_item_index(items, after_id)
        if anchor_index is None:
            raise CliError(f"Anchor item not found: {after_id}")
        items.insert(anchor_index + 1, item)
        return item

    if existing_index is None:
        items.append(item)
        return item

    items.insert(existing_index, item)
    return item


def yaml_quoted(value: str) -> str:
    return json.dumps(value)


def phase_heading(todo_id: str) -> str:
    return todo_id.replace("_", " ").replace("-", " ").title()


def render_plan(title: str, overview: str, todos: list[tuple[str, str]], is_project: bool) -> str:
    lines: list[str] = [
        "---",
        f"name: {yaml_quoted(title.lower())}",
        f"overview: {yaml_quoted(overview)}",
        "todos:",
    ]
    for todo_id, content in todos:
        lines.extend(
            [
                f"  - id: {yaml_quoted(todo_id)}",
                f"    content: {yaml_quoted(content)}",
                "    status: pending",
            ]
        )
    lines.extend(
        [
            f"isProject: {'true' if is_project else 'false'}",
            "---",
            "",
            f"# {title}",
            "",
            "## Scope Decision",
            "",
            "- Define the exact requested scope here.",
            "- List the rejected scope expansions here.",
            "",
            "## Ownership Target",
            "",
            "- `Runtime owner`: ...",
            "- `First fix owner`: ...",
            "- `Canonical long-term owner`: ...",
            "- `Wrong competing owners`: ...",
            "",
            "## Existing Leverage",
            "",
            "- List the concrete files, symbols, tests, and existing behavior this plan will reuse or narrow.",
            "",
        ]
    )
    for index, (todo_id, content) in enumerate(todos, start=1):
        lines.extend(
            [
                f"## Phase {index}: {phase_heading(todo_id)}",
                "",
                "Phase goal:",
                "",
                f"- {content}",
                "",
                "Tasks:",
                "",
                f"- [ ] {content}",
                "- [ ] Reconcile the scoped diff and recorded verification before marking this phase complete.",
                "",
            ]
        )
    lines.extend(
        [
            "## Out Of Scope",
            "",
            "- Fill in the adjacent work this plan will not absorb.",
            "",
            "## Verification",
            "",
            "- `git diff -- <owned paths>`",
            "- `<focused verification command>`",
            "",
            "## Acceptance Criteria",
            "",
        ]
    )
    for _, content in todos:
        lines.append(f"- {content}")
    lines.append("")
    return "\n".join(lines)


def parse_todos(raw_todos: list[str]) -> list[tuple[str, str]]:
    todos: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in raw_todos:
        todo_id, sep, content = raw.partition("=")
        todo_id = todo_id.strip()
        content = content.strip()
        if not sep or not todo_id or not content:
            raise CliError("Each `--todo` must use the form `id=content`.")
        if todo_id in seen:
            raise CliError(f"Duplicate todo id: {todo_id}")
        seen.add(todo_id)
        todos.append((todo_id, content))
    if not todos:
        raise CliError("At least one `--todo id=content` entry is required.")
    return todos


def cmd_plan_new(args: argparse.Namespace, root: Path) -> int:
    title = args.title.strip()
    if not title:
        raise CliError("`--title` cannot be empty.")
    overview = args.overview.strip()
    if not overview:
        raise CliError("`--overview` cannot be empty.")

    todos = parse_todos(args.todo)
    slug = slugify(args.slug or title)
    filename = f"{slug}_{title_hash(title)}.plan.md"
    plan_path = root / PLANS_DIR / filename
    if plan_path.exists() and not args.force:
        raise CliError(f"Plan already exists: {plan_path.relative_to(root).as_posix()}")

    content = render_plan(title=title, overview=overview, todos=todos, is_project=args.is_project)
    atomic_write_text(plan_path, content)
    print(plan_path.relative_to(root).as_posix())
    return 0


def cmd_status_show(args: argparse.Namespace, root: Path) -> int:
    data = load_status(root)
    if args.scope:
        payload = require_scope(data, args.scope)
    else:
        payload = data
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def open_scope_sort_key(summary: dict[str, Any]) -> tuple[int, int, str]:
    status = summary["status"]
    if status == "in_progress":
        bucket = 0
    elif status == "pending":
        bucket = 1
    elif status == "blocked":
        bucket = 2
    else:
        bucket = 3
    return (bucket, summary["_order"], summary["id"])


def summarize_open_scope(scope: dict[str, Any], index: int) -> dict[str, Any] | None:
    raw_scope_id = scope.get("id")
    if not isinstance(raw_scope_id, str) or not raw_scope_id.strip():
        raise CliError(f"`scopes[{index}].id` must be a non-empty string in `.planr/status/current.json`.")
    scope_id = raw_scope_id.strip()

    status = require_valid_status(scope.get("status"), VALID_SCOPE_STATUSES, f"`{scope_id}.status`")
    checklist_items = get_object_list(scope, "checklist", scope_id)
    blocked_items = get_object_list(scope, "blocked_or_unverified", scope_id)
    verification_items = get_object_list(scope, "verification", scope_id)

    open_checklist_ids: list[str] = []
    for checklist_index, item in enumerate(checklist_items):
        checklist_status = require_valid_status(
            item.get("status"),
            VALID_CHECKLIST_STATUSES,
            f"`{scope_id}.checklist[{checklist_index}].status`",
        )
        if checklist_status in OPEN_SCOPE_STATUSES:
            item_id = item.get("id")
            open_checklist_ids.append(item_id if isinstance(item_id, str) and item_id else f"checklist[{checklist_index}]")

    blocked_or_unverified_ids: list[str] = []
    for blocker_index, item in enumerate(blocked_items):
        blocker_status = require_valid_status(
            item.get("status"),
            VALID_BLOCKER_STATUSES,
            f"`{scope_id}.blocked_or_unverified[{blocker_index}].status`",
        )
        if blocker_status in VALID_BLOCKER_STATUSES:
            item_id = item.get("id")
            blocked_or_unverified_ids.append(
                item_id if isinstance(item_id, str) and item_id else f"blocked_or_unverified[{blocker_index}]"
            )

    non_passed_verification_ids: list[str] = []
    for verification_index, item in enumerate(verification_items):
        verification_status = require_valid_status(
            item.get("status"),
            VALID_VERIFICATION_STATUSES,
            f"`{scope_id}.verification[{verification_index}].status`",
        )
        if verification_status in NON_PASSED_VERIFICATION_STATUSES:
            item_id = item.get("id")
            non_passed_verification_ids.append(
                item_id if isinstance(item_id, str) and item_id else f"verification[{verification_index}]"
            )

    status_drift = status in {"completed", "cancelled"} and bool(
        open_checklist_ids or blocked_or_unverified_ids or non_passed_verification_ids
    )
    is_open = status in OPEN_SCOPE_STATUSES or status_drift
    if not is_open:
        return None

    title = scope.get("title")
    plan_paths = get_list_field(scope, "plan_paths", scope_id)
    return {
        "id": scope_id,
        "title": title if isinstance(title, str) else "",
        "status": status,
        "plan_paths": plan_paths,
        "open_checklist_count": len(open_checklist_ids),
        "open_checklist_ids": open_checklist_ids,
        "blocked_or_unverified_count": len(blocked_or_unverified_ids),
        "blocked_or_unverified_ids": blocked_or_unverified_ids,
        "non_passed_verification_count": len(non_passed_verification_ids),
        "non_passed_verification_ids": non_passed_verification_ids,
        "status_drift": status_drift,
        "_order": index,
    }


def sorted_open_scope_summaries(data: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, scope in enumerate(scopes(data)):
        summary = summarize_open_scope(scope, index)
        if summary is not None:
            summaries.append(summary)
    summaries.sort(key=open_scope_sort_key)
    return summaries


def public_scope_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if not key.startswith("_")}


def cmd_status_open(args: argparse.Namespace, root: Path) -> int:
    del args
    data = load_status(root)
    payload = [public_scope_summary(summary) for summary in sorted_open_scope_summaries(data)]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_status_next(args: argparse.Namespace, root: Path) -> int:
    del args
    data = load_status(root)
    summaries = sorted_open_scope_summaries(data)

    actionable = [summary for summary in summaries if summary["status"] in OPEN_SCOPE_STATUSES]
    if actionable:
        payload = public_scope_summary(actionable[0])
        payload["selection_reason"] = (
            "selected the first actionable open scope by status precedence "
            "(in_progress, pending, blocked) and scope order"
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if summaries:
        payload = public_scope_summary(summaries[0])
        payload["selection_reason"] = (
            "no actionable in_progress, pending, or blocked scopes remain; "
            "returning the first closed scope with status drift"
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("null")
    return 0


def cmd_status_ensure_scope(args: argparse.Namespace, root: Path) -> int:
    data = load_status(root)
    scope = find_scope(data, args.id)
    if scope is None:
        scope = {
            "id": args.id,
            "title": "",
            "status": "pending",
            "source": "",
            "plan_paths": [],
            "owned_paths": [],
            "checklist": [],
            "verification": [],
            "blocked_or_unverified": [],
        }
        scopes(data).append(scope)

    if args.title is not None:
        scope["title"] = args.title
    if args.status is not None:
        scope["status"] = args.status
    if args.source is not None:
        scope["source"] = args.source
    if args.plan_path is not None:
        scope["plan_paths"] = normalize_unique_paths(root, args.plan_path)
    if args.owned_path is not None:
        scope["owned_paths"] = normalize_unique_paths(root, args.owned_path)

    save_status(root, data)
    print(json.dumps(scope, indent=2, ensure_ascii=False))
    return 0


def cmd_status_set_checklist(args: argparse.Namespace, root: Path) -> int:
    data = load_status(root)
    scope = require_scope(data, args.scope)
    items = require_list_field(scope, "checklist", args.scope)
    item = upsert_item(items, args.item_id, before_id=args.before_id, after_id=args.after_id)
    if args.content is not None:
        item["content"] = args.content
    elif "content" not in item:
        raise CliError("`--content` is required when creating a new checklist item.")
    item["status"] = args.status
    save_status(root, data)
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0


def cmd_status_set_blocker(args: argparse.Namespace, root: Path) -> int:
    data = load_status(root)
    scope = require_scope(data, args.scope)
    items = require_list_field(scope, "blocked_or_unverified", args.scope)
    item = upsert_item(items, args.item_id, before_id=args.before_id, after_id=args.after_id)
    if args.content is not None:
        item["content"] = args.content
    elif "content" not in item:
        raise CliError("`--content` is required when creating a new blocker or unverified item.")
    item["status"] = args.status
    save_status(root, data)
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0


def cmd_status_set_verification(args: argparse.Namespace, root: Path) -> int:
    data = load_status(root)
    scope = require_scope(data, args.scope)
    items = require_list_field(scope, "verification", args.scope)
    item = upsert_item(items, args.verification_id, before_id=args.before_id, after_id=args.after_id)
    item["status"] = args.status
    item["result"] = args.result
    if args.command is not None:
        item["command"] = args.command
    save_status(root, data)
    print(json.dumps(item, indent=2, ensure_ascii=False))
    return 0


def add_relative_order_arguments(parser: argparse.ArgumentParser) -> None:
    ordering = parser.add_mutually_exclusive_group()
    ordering.add_argument("--before-id", help="Insert or move the item before the given sibling item id.")
    ordering.add_argument("--after-id", help="Insert or move the item after the given sibling item id.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic local helper CLI for `.planr` plan and status files.")
    parser.add_argument("--repo-root", help="Repo root containing `.planr/`. Defaults to the current repo root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Deterministic `.planr/plans` helpers.")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_command", required=True)

    plan_new = plan_subparsers.add_parser("new", help="Create a deterministic `.planr/plans/*.plan.md` scaffold.")
    plan_new.add_argument("--title", required=True, help="Display title for the plan.")
    plan_new.add_argument("--overview", required=True, help="One-paragraph overview for the plan frontmatter.")
    plan_new.add_argument("--todo", action="append", default=[], help="Todo entry in the form `id=content`.")
    plan_new.add_argument("--slug", help="Optional explicit filename slug. Defaults to a slugified title.")
    plan_new.add_argument("--project", dest="is_project", action="store_true", help="Set `isProject: true`.")
    plan_new.add_argument("--force", action="store_true", help="Overwrite an existing deterministic output path.")
    plan_new.set_defaults(func=cmd_plan_new)

    status_parser = subparsers.add_parser("status", help="Deterministic `.planr/status/current.json` helpers.")
    status_subparsers = status_parser.add_subparsers(dest="status_command", required=True)

    status_show = status_subparsers.add_parser("show", help="Print the current status JSON or one scope.")
    status_show.add_argument("--scope", help="Optional scope id to print only one scope.")
    status_show.set_defaults(func=cmd_status_show)

    status_open = status_subparsers.add_parser(
        "open",
        help="List open scopes, including closed scopes whose subordinate state still indicates unfinished work.",
    )
    status_open.set_defaults(func=cmd_status_open)

    status_next = status_subparsers.add_parser(
        "next",
        help="Select the next deterministic open scope, preferring actionable in-progress or pending work.",
    )
    status_next.set_defaults(func=cmd_status_next)

    ensure_scope = status_subparsers.add_parser("ensure-scope", help="Create or update a scope entry.")
    ensure_scope.add_argument("--id", required=True, help="Scope id.")
    ensure_scope.add_argument("--title", help="Scope title.")
    ensure_scope.add_argument("--status", choices=sorted(VALID_SCOPE_STATUSES), help="Scope status.")
    ensure_scope.add_argument("--source", help="Scope source note.")
    ensure_scope.add_argument("--plan-path", action="append", help="Plan path to store on the scope. Repeatable.")
    ensure_scope.add_argument("--owned-path", action="append", help="Owned path to store on the scope. Repeatable.")
    ensure_scope.set_defaults(func=cmd_status_ensure_scope)

    set_checklist = status_subparsers.add_parser("set-checklist", help="Create or update one checklist item.")
    set_checklist.add_argument("--scope", required=True, help="Scope id.")
    set_checklist.add_argument("--item-id", required=True, help="Checklist item id.")
    set_checklist.add_argument("--content", help="Checklist item content. Required when creating a new item.")
    set_checklist.add_argument("--status", required=True, choices=sorted(VALID_CHECKLIST_STATUSES), help="Checklist item status.")
    add_relative_order_arguments(set_checklist)
    set_checklist.set_defaults(func=cmd_status_set_checklist)

    set_blocker = status_subparsers.add_parser("set-blocker", help="Create or update one blocked or unverified item.")
    set_blocker.add_argument("--scope", required=True, help="Scope id.")
    set_blocker.add_argument("--item-id", required=True, help="Blocked or unverified item id.")
    set_blocker.add_argument("--content", help="Blocked or unverified item content. Required when creating a new item.")
    set_blocker.add_argument("--status", required=True, choices=sorted(VALID_BLOCKER_STATUSES), help="Blocked or unverified item status.")
    add_relative_order_arguments(set_blocker)
    set_blocker.set_defaults(func=cmd_status_set_blocker)

    set_verification = status_subparsers.add_parser("set-verification", help="Create or update one verification record.")
    set_verification.add_argument("--scope", required=True, help="Scope id.")
    set_verification.add_argument("--verification-id", required=True, help="Verification record id.")
    set_verification.add_argument("--status", required=True, choices=sorted(VALID_VERIFICATION_STATUSES), help="Verification status.")
    set_verification.add_argument("--result", required=True, help="Human-readable verification result.")
    set_verification.add_argument("--command", help="Optional exact command string for the verification record.")
    add_relative_order_arguments(set_verification)
    set_verification.set_defaults(func=cmd_status_set_verification)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = resolve_repo_root(args.repo_root)
        return args.func(args, root)
    except CliError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
