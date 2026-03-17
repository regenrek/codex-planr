#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / ".planr" / "tooling" / "planr.py"
LAUNCHER_PATH = REPO_ROOT / ".planr" / "tooling" / "planr"
TEST_LAUNCHER_PATH = REPO_ROOT / ".planr" / "tooling" / "test_planr"
SKILLS_ROOT = REPO_ROOT / ".codex" / "skills"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_status_fixture(root: Path, *, scopes: list[dict] | None = None) -> None:
    status_path = root / ".planr" / "status" / "current.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2026-03-17T00:00:00Z",
                "global_status": "in_progress",
                "project_context": {"root": ".planr/project", "files": []},
                "notes": [],
                "scopes": scopes or [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class PlanrCliTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-root", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_plan_new_creates_deterministic_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(root)

            result = self.run_cli(
                root,
                "plan",
                "new",
                "--title",
                "Planr Python CLI",
                "--overview",
                "Deterministic local planr CLI.",
                "--todo",
                "lock-cli-contract=Define the minimal deterministic planr CLI surface.",
                "--todo",
                "verify-cli=Add focused tests proving deterministic output.",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), ".planr/plans/planr_python_cli_e4aded5b.plan.md")

            plan_path = root / result.stdout.strip()
            content = plan_path.read_text(encoding="utf-8")
            self.assertIn('name: "planr python cli"', content)
            self.assertIn('"lock-cli-contract"', content)
            self.assertIn("## Phase 1: Lock Cli Contract", content)
            self.assertIn("## Acceptance Criteria", content)

            duplicate = self.run_cli(
                root,
                "plan",
                "new",
                "--title",
                "Planr Python CLI",
                "--overview",
                "Deterministic local planr CLI.",
                "--todo",
                "lock-cli-contract=Define the minimal deterministic planr CLI surface.",
            )
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("Plan already exists", duplicate.stderr)

    def test_plan_new_force_overwrites_and_project_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(root)

            create = self.run_cli(
                root,
                "plan",
                "new",
                "--title",
                "Planr Python CLI",
                "--overview",
                "First version.",
                "--todo",
                "lock-cli-contract=Define the minimal deterministic planr CLI surface.",
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            plan_path = root / create.stdout.strip()
            plan_path.write_text("stale\n", encoding="utf-8")

            overwrite = self.run_cli(
                root,
                "plan",
                "new",
                "--title",
                "Planr Python CLI",
                "--overview",
                "Second version.",
                "--todo",
                "lock-cli-contract=Define the minimal deterministic planr CLI surface.",
                "--project",
                "--force",
            )
            self.assertEqual(overwrite.returncode, 0, overwrite.stderr)

            content = plan_path.read_text(encoding="utf-8")
            self.assertIn('overview: "Second version."', content)
            self.assertIn("isProject: true", content)
            self.assertNotEqual(content, "stale\n")

    def test_status_commands_upsert_scope_items_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(root)

            ensure_scope = self.run_cli(
                root,
                "status",
                "ensure-scope",
                "--id",
                "planr-python-cli",
                "--title",
                "Planr Python CLI",
                "--status",
                "in_progress",
                "--source",
                "user-requested planr-fix",
                "--plan-path",
                ".planr/plans/planr_python_cli_e4aded5b.plan.md",
                "--owned-path",
                ".planr/tooling/planr.py",
                "--owned-path",
                ".planr/tooling/test_planr.py",
            )
            self.assertEqual(ensure_scope.returncode, 0, ensure_scope.stderr)

            set_checklist = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "lock-cli-contract",
                "--content",
                "Define the minimal deterministic planr CLI surface.",
                "--status",
                "in_progress",
            )
            self.assertEqual(set_checklist.returncode, 0, set_checklist.stderr)

            update_checklist = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "lock-cli-contract",
                "--status",
                "completed",
            )
            self.assertEqual(update_checklist.returncode, 0, update_checklist.stderr)

            set_blocker = self.run_cli(
                root,
                "status",
                "set-blocker",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "needs-review",
                "--content",
                "Review the initial CLI command surface.",
                "--status",
                "blocked",
            )
            self.assertEqual(set_blocker.returncode, 0, set_blocker.stderr)

            set_verification = self.run_cli(
                root,
                "status",
                "set-verification",
                "--scope",
                "planr-python-cli",
                "--verification-id",
                "cli-help",
                "--status",
                "passed",
                "--result",
                "CLI help rendered successfully.",
                "--command",
                "./.planr/tooling/planr --help",
            )
            self.assertEqual(set_verification.returncode, 0, set_verification.stderr)

            show_scope = self.run_cli(root, "status", "show", "--scope", "planr-python-cli")
            self.assertEqual(show_scope.returncode, 0, show_scope.stderr)
            scope = json.loads(show_scope.stdout)

            self.assertEqual(scope["title"], "Planr Python CLI")
            self.assertEqual(scope["status"], "in_progress")
            self.assertEqual(scope["plan_paths"], [".planr/plans/planr_python_cli_e4aded5b.plan.md"])
            self.assertEqual(scope["owned_paths"], [".planr/tooling/planr.py", ".planr/tooling/test_planr.py"])
            self.assertEqual(
                scope["checklist"],
                [
                    {
                        "id": "lock-cli-contract",
                        "content": "Define the minimal deterministic planr CLI surface.",
                        "status": "completed",
                    }
                ],
            )
            self.assertEqual(
                scope["blocked_or_unverified"],
                [
                    {
                        "id": "needs-review",
                        "content": "Review the initial CLI command surface.",
                        "status": "blocked",
                    }
                ],
            )
            self.assertEqual(
                scope["verification"],
                [
                    {
                        "id": "cli-help",
                        "status": "passed",
                        "result": "CLI help rendered successfully.",
                        "command": "./.planr/tooling/planr --help",
                    }
                ],
            )

            full_status = json.loads((root / ".planr" / "status" / "current.json").read_text(encoding="utf-8"))
            self.assertRegex(full_status["updated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_status_item_mutations_support_relative_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "planr-python-cli",
                        "title": "Planr Python CLI",
                        "status": "in_progress",
                        "source": "user-requested planr-fix",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [
                            {"id": "phase-1", "content": "Phase 1.", "status": "pending"},
                            {"id": "verify", "content": "Verify.", "status": "pending"},
                        ],
                        "verification": [
                            {"id": "diff", "status": "passed", "result": "Diff clean."},
                            {"id": "tests", "status": "not_run", "result": "Not run yet."},
                        ],
                        "blocked_or_unverified": [
                            {"id": "api", "content": "Need API.", "status": "blocked"},
                            {"id": "docs", "content": "Need docs.", "status": "unverified"},
                        ],
                    }
                ],
            )

            set_checklist = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "phase-2",
                "--content",
                "Phase 2.",
                "--status",
                "pending",
                "--before-id",
                "verify",
            )
            self.assertEqual(set_checklist.returncode, 0, set_checklist.stderr)

            move_blocker = self.run_cli(
                root,
                "status",
                "set-blocker",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "docs",
                "--status",
                "unverified",
                "--before-id",
                "api",
            )
            self.assertEqual(move_blocker.returncode, 0, move_blocker.stderr)

            move_verification = self.run_cli(
                root,
                "status",
                "set-verification",
                "--scope",
                "planr-python-cli",
                "--verification-id",
                "tests",
                "--status",
                "not_run",
                "--result",
                "Not run yet.",
                "--before-id",
                "diff",
            )
            self.assertEqual(move_verification.returncode, 0, move_verification.stderr)

            show_scope = self.run_cli(root, "status", "show", "--scope", "planr-python-cli")
            self.assertEqual(show_scope.returncode, 0, show_scope.stderr)
            scope = json.loads(show_scope.stdout)

            self.assertEqual([item["id"] for item in scope["checklist"]], ["phase-1", "phase-2", "verify"])
            self.assertEqual([item["id"] for item in scope["blocked_or_unverified"]], ["docs", "api"])
            self.assertEqual([item["id"] for item in scope["verification"]], ["tests", "diff"])

    def test_status_open_lists_open_and_drifted_scopes_in_deterministic_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "completed-clean",
                        "title": "Completed Clean",
                        "status": "completed",
                        "source": "",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [{"id": "done", "content": "Done.", "status": "completed"}],
                        "verification": [{"id": "verify", "status": "passed", "result": "ok"}],
                        "blocked_or_unverified": [],
                    },
                    {
                        "id": "pending-scope",
                        "title": "Pending Scope",
                        "status": "pending",
                        "source": "",
                        "plan_paths": [".planr/plans/pending.plan.md"],
                        "owned_paths": [],
                        "checklist": [],
                        "verification": [],
                        "blocked_or_unverified": [],
                    },
                    {
                        "id": "drifted-completed",
                        "title": "Drifted Completed",
                        "status": "completed",
                        "source": "",
                        "plan_paths": [".planr/plans/drifted.plan.md"],
                        "owned_paths": [],
                        "checklist": [{"id": "still-open", "content": "Still open.", "status": "in_progress"}],
                        "verification": [],
                        "blocked_or_unverified": [],
                    },
                    {
                        "id": "in-progress-scope",
                        "title": "In Progress Scope",
                        "status": "in_progress",
                        "source": "",
                        "plan_paths": [".planr/plans/in-progress.plan.md"],
                        "owned_paths": [],
                        "checklist": [{"id": "ship-it", "content": "Ship it.", "status": "in_progress"}],
                        "verification": [{"id": "tests", "status": "failed", "result": "tests failed"}],
                        "blocked_or_unverified": [],
                    },
                    {
                        "id": "blocked-scope",
                        "title": "Blocked Scope",
                        "status": "blocked",
                        "source": "",
                        "plan_paths": [".planr/plans/blocked.plan.md"],
                        "owned_paths": [],
                        "checklist": [],
                        "verification": [],
                        "blocked_or_unverified": [{"id": "needs-api", "content": "Need API.", "status": "blocked"}],
                    },
                ],
            )

            result = self.run_cli(root, "status", "open")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)

            self.assertEqual(
                [item["id"] for item in payload],
                ["in-progress-scope", "pending-scope", "blocked-scope", "drifted-completed"],
            )
            self.assertEqual(payload[0]["open_checklist_ids"], ["ship-it"])
            self.assertEqual(payload[0]["non_passed_verification_ids"], ["tests"])
            self.assertEqual(payload[1]["plan_paths"], [".planr/plans/pending.plan.md"])
            self.assertEqual(payload[2]["blocked_or_unverified_ids"], ["needs-api"])
            self.assertTrue(payload[3]["status_drift"])

    def test_status_next_prefers_first_actionable_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "drifted-completed",
                        "title": "Drifted Completed",
                        "status": "completed",
                        "source": "",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [{"id": "still-open", "content": "Still open.", "status": "pending"}],
                        "verification": [],
                        "blocked_or_unverified": [],
                    },
                    {
                        "id": "pending-scope",
                        "title": "Pending Scope",
                        "status": "pending",
                        "source": "",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [],
                        "verification": [],
                        "blocked_or_unverified": [],
                    },
                    {
                        "id": "in-progress-scope",
                        "title": "In Progress Scope",
                        "status": "in_progress",
                        "source": "",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [{"id": "do-work", "content": "Do work.", "status": "in_progress"}],
                        "verification": [],
                        "blocked_or_unverified": [],
                    },
                ],
            )

            result = self.run_cli(root, "status", "next")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)

            self.assertEqual(payload["id"], "in-progress-scope")
            self.assertFalse(payload["status_drift"])
            self.assertIn("first actionable open scope", payload["selection_reason"])

    def test_status_next_falls_back_to_drift_when_no_actionable_scope_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "drifted-completed",
                        "title": "Drifted Completed",
                        "status": "completed",
                        "source": "",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [{"id": "still-open", "content": "Still open.", "status": "pending"}],
                        "verification": [],
                        "blocked_or_unverified": [],
                    }
                ],
            )

            result = self.run_cli(root, "status", "next")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)

            self.assertEqual(payload["id"], "drifted-completed")
            self.assertTrue(payload["status_drift"])
            self.assertIn("status drift", payload["selection_reason"])

    def test_status_next_returns_null_when_every_scope_is_cleanly_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "completed-clean",
                        "title": "Completed Clean",
                        "status": "completed",
                        "source": "",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [{"id": "done", "content": "Done.", "status": "completed"}],
                        "verification": [{"id": "verify", "status": "passed", "result": "ok"}],
                        "blocked_or_unverified": [],
                    }
                ],
            )

            result = self.run_cli(root, "status", "next")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "null")

    def test_project_init_creates_project_pack_and_status_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".planr").mkdir(parents=True, exist_ok=True)

            result = self.run_cli(root, "project", "init")
            self.assertEqual(result.returncode, 0, result.stderr)

            payload = json.loads(result.stdout)
            expected_files = [
                ".planr/project/product.md",
                ".planr/project/ownership.md",
                ".planr/project/flows.md",
                ".planr/project/state-ssot.md",
                ".planr/project/constraints.md",
                ".planr/project/quality-gates.md",
            ]

            self.assertEqual(payload["project_root"], ".planr/project")
            self.assertEqual(payload["written"], expected_files)
            self.assertEqual(payload["preserved_existing"], [])
            self.assertEqual(payload["project_context_files"], expected_files)
            self.assertIn("Inspect the target codebase and rewrite `.planr/project/*.md`", payload["next_step"])

            ownership = read_text(root / ".planr" / "project" / "ownership.md")
            self.assertIn("Define **your** codebase’s layers", ownership)

            status = json.loads(read_text(root / ".planr" / "status" / "current.json"))
            self.assertEqual(status["project_context"]["root"], ".planr/project")
            self.assertEqual(status["project_context"]["files"], expected_files)
            self.assertEqual(status["global_status"], "open")
            self.assertEqual(status["scopes"], [])

    def test_project_init_preserves_existing_files_without_force_and_overwrites_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(root)

            project_root = root / ".planr" / "project"
            project_root.mkdir(parents=True, exist_ok=True)
            ownership_path = project_root / "ownership.md"
            ownership_path.write_text("# Ownership\n\ncustom\n", encoding="utf-8")

            first = self.run_cli(root, "project", "init")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)

            self.assertIn(".planr/project/ownership.md", first_payload["preserved_existing"])
            self.assertEqual(read_text(ownership_path), "# Ownership\n\ncustom\n")

            second = self.run_cli(root, "project", "init", "--force")
            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second.stdout)

            self.assertIn(".planr/project/ownership.md", second_payload["written"])
            self.assertIn("Define **your** codebase’s layers", read_text(ownership_path))

    def test_invalid_repo_root_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.run_cli(
                root,
                "plan",
                "new",
                "--title",
                "Planr Python CLI",
                "--overview",
                "Deterministic local planr CLI.",
                "--todo",
                "lock-cli-contract=Define the minimal deterministic planr CLI surface.",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not contain `.planr/`", result.stderr)

    def test_invalid_todo_and_missing_content_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(root)

            invalid_todo = self.run_cli(
                root,
                "plan",
                "new",
                "--title",
                "Planr Python CLI",
                "--overview",
                "Deterministic local planr CLI.",
                "--todo",
                "missing-separator",
            )
            self.assertNotEqual(invalid_todo.returncode, 0)
            self.assertIn("Each `--todo` must use the form", invalid_todo.stderr)


class PlanrSkillSmokeTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-root", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_launchers_exist_and_are_executable(self) -> None:
        self.assertTrue(LAUNCHER_PATH.is_file())
        self.assertTrue(TEST_LAUNCHER_PATH.is_file())
        self.assertTrue(os.access(LAUNCHER_PATH, os.X_OK))
        self.assertTrue(os.access(TEST_LAUNCHER_PATH, os.X_OK))

        planr_help = subprocess.run(
            [str(LAUNCHER_PATH), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )
        self.assertEqual(planr_help.returncode, 0, planr_help.stderr)
        self.assertIn("{project,plan,status}", planr_help.stdout)

        test_help = subprocess.run(
            [str(TEST_LAUNCHER_PATH), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )
        self.assertEqual(test_help.returncode, 0, test_help.stderr)
        self.assertIn("usage:", test_help.stdout + test_help.stderr)

    def test_shared_baseline_exists_and_setup_docs_copy_it(self) -> None:
        shared_path = SKILLS_ROOT / "planr-shared.md"
        readme = read_text(REPO_ROOT / "README.md")

        self.assertTrue(shared_path.is_file())
        self.assertIn("cp /path/to/codex-planr/.codex/skills/planr-shared.md .codex/skills/", readme)
        self.assertIn("planr-shared.md", readme)

    def test_shared_baseline_documents_actual_cli_surface(self) -> None:
        shared = read_text(SKILLS_ROOT / "planr-shared.md")

        expected_commands = [
            "./.planr/tooling/planr project init",
            "./.planr/tooling/planr plan new",
            "./.planr/tooling/planr status show",
            "./.planr/tooling/planr status open",
            "./.planr/tooling/planr status next",
            "./.planr/tooling/planr status ensure-scope",
            "./.planr/tooling/planr status set-checklist",
            "./.planr/tooling/planr status set-blocker",
            "./.planr/tooling/planr status set-verification",
        ]
        for command in expected_commands:
            self.assertIn(command, shared)

        self.assertIn("There is no `planr.py fix` command today.", shared)
        self.assertIn("There is no `planr.py review` command today.", shared)
        self.assertIn("project init` only scaffolds or refreshes `.planr/project/*.md`", shared)

    def test_repo_local_planr_skills_reference_shared_baseline(self) -> None:
        for skill_name in ["planr-fix", "planr-plan", "planr-review", "planr-status", "planr-summary"]:
            skill_md = read_text(SKILLS_ROOT / skill_name / "SKILL.md")
            reference_md = read_text(SKILLS_ROOT / skill_name / "reference.md")

            self.assertIn("[../planr-shared.md](../planr-shared.md)", skill_md, skill_name)
            self.assertIn("[reference.md](reference.md)", skill_md, skill_name)
            self.assertIn("[../planr-shared.md](../planr-shared.md)", reference_md, skill_name)

    def test_skill_docs_only_claim_supported_cli_subcommands(self) -> None:
        shared = read_text(SKILLS_ROOT / "planr-shared.md")
        fix_skill = read_text(SKILLS_ROOT / "planr-fix" / "SKILL.md")
        review_skill = read_text(SKILLS_ROOT / "planr-review" / "SKILL.md")
        plan_skill = read_text(SKILLS_ROOT / "planr-plan" / "SKILL.md")

        self.assertIn("There is no `planr.py fix` command today.", fix_skill)
        self.assertIn("There is no `planr.py review` command today.", review_skill)
        self.assertIn("There is no general plan-update command today.", plan_skill)
        self.assertIn("Today the CLI supports `project`, `plan`, and `status`.", shared)

    def test_readmes_document_project_init_and_codebase_rewrite_step(self) -> None:
        root_readme = read_text(REPO_ROOT / "README.md")
        planr_readme = read_text(REPO_ROOT / ".planr" / "README.md")

        self.assertIn("./.planr/tooling/planr project init", root_readme)
        self.assertIn("rewrite `.planr/project/*.md`", root_readme)
        self.assertIn("./.planr/tooling/planr project init", planr_readme)
        self.assertIn("inspect the target codebase and rewrite `.planr/project/*.md`", planr_readme)

    def test_missing_checklist_content_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(root)

            ensure_scope = self.run_cli(
                root,
                "status",
                "ensure-scope",
                "--id",
                "planr-python-cli",
                "--title",
                "Planr Python CLI",
            )
            self.assertEqual(ensure_scope.returncode, 0, ensure_scope.stderr)

            missing_content = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "lock-cli-contract",
                "--status",
                "pending",
            )
            self.assertNotEqual(missing_content.returncode, 0)
            self.assertIn("`--content` is required", missing_content.stderr)

    def test_relative_ordering_fails_for_missing_or_self_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "planr-python-cli",
                        "title": "Planr Python CLI",
                        "status": "in_progress",
                        "source": "user-requested planr-fix",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [{"id": "phase-1", "content": "Phase 1.", "status": "pending"}],
                        "verification": [],
                        "blocked_or_unverified": [],
                    }
                ],
            )

            missing_anchor = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "phase-2",
                "--content",
                "Phase 2.",
                "--status",
                "pending",
                "--before-id",
                "verify",
            )
            self.assertNotEqual(missing_anchor.returncode, 0)
            self.assertIn("Anchor item not found: verify", missing_anchor.stderr)

            self_anchor = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "phase-1",
                "--status",
                "pending",
                "--before-id",
                "phase-1",
            )
            self.assertNotEqual(self_anchor.returncode, 0)
            self.assertIn("cannot be positioned relative to itself", self_anchor.stderr)

    def test_paths_outside_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(temp_dir)
            outside = Path(outside_dir).resolve()
            write_status_fixture(root)

            relative_escape = self.run_cli(
                root,
                "status",
                "ensure-scope",
                "--id",
                "planr-python-cli",
                "--title",
                "Planr Python CLI",
                "--plan-path",
                "../outside.plan.md",
            )
            self.assertNotEqual(relative_escape.returncode, 0)
            self.assertIn("Path must stay inside the repo root", relative_escape.stderr)

            absolute_escape = self.run_cli(
                root,
                "status",
                "ensure-scope",
                "--id",
                "planr-python-cli",
                "--title",
                "Planr Python CLI",
                "--owned-path",
                str(outside / "escape.py"),
            )
            self.assertNotEqual(absolute_escape.returncode, 0)
            self.assertIn("Path must stay inside the repo root", absolute_escape.stderr)

    def test_malformed_checklist_list_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "planr-python-cli",
                        "title": "Planr Python CLI",
                        "status": "in_progress",
                        "source": "user-requested planr-fix",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": {},
                        "verification": [],
                        "blocked_or_unverified": [],
                    }
                ],
            )
            result = self.run_cli(
                root,
                "status",
                "set-checklist",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "lock-cli-contract",
                "--content",
                "Define the minimal deterministic planr CLI surface.",
                "--status",
                "pending",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("`planr-python-cli.checklist` must be a list", result.stderr)

    def test_malformed_blocker_list_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "planr-python-cli",
                        "title": "Planr Python CLI",
                        "status": "in_progress",
                        "source": "user-requested planr-fix",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [],
                        "verification": [],
                        "blocked_or_unverified": {},
                    }
                ],
            )
            result = self.run_cli(
                root,
                "status",
                "set-blocker",
                "--scope",
                "planr-python-cli",
                "--item-id",
                "needs-review",
                "--content",
                "Review the initial CLI command surface.",
                "--status",
                "blocked",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("`planr-python-cli.blocked_or_unverified` must be a list", result.stderr)

    def test_malformed_verification_list_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_status_fixture(
                root,
                scopes=[
                    {
                        "id": "planr-python-cli",
                        "title": "Planr Python CLI",
                        "status": "in_progress",
                        "source": "user-requested planr-fix",
                        "plan_paths": [],
                        "owned_paths": [],
                        "checklist": [],
                        "verification": {},
                        "blocked_or_unverified": [],
                    }
                ],
            )
            result = self.run_cli(
                root,
                "status",
                "set-verification",
                "--scope",
                "planr-python-cli",
                "--verification-id",
                "cli-help",
                "--status",
                "passed",
                "--result",
                "CLI help rendered successfully.",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("`planr-python-cli.verification` must be a list", result.stderr)


if __name__ == "__main__":
    unittest.main()
