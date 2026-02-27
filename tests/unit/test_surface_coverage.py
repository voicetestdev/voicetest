"""Surface coverage tests — verify every service method is wired to a transport.

Also verifies methods are explicitly listed in INTERNAL_ONLY if not surfaced.

When a new public method is added to any service class, these tests fail until the
method is listed in one of the transport coverage sets or added to INTERNAL_ONLY
with a justification.
"""

import ast
from pathlib import Path

import pytest


SERVICES_DIR = Path(__file__).resolve().parents[2] / "voicetest" / "services"


def _discover_service_methods() -> dict[str, set[str]]:
    """AST-scan all service classes and return {ClassName: {method_names}}."""
    results: dict[str, set[str]] = {}
    for py in sorted(SERVICES_DIR.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Service"):
                methods = set()
                for item in node.body:
                    is_func = isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    if is_func and not item.name.startswith("_"):
                        methods.add(item.name)
                if methods:
                    results[node.name] = methods
    return results


def _all_qualified() -> set[str]:
    """Return all 'ClassName.method' strings discovered from services."""
    qualified = set()
    for cls, methods in _discover_service_methods().items():
        for m in methods:
            qualified.add(f"{cls}.{m}")
    return qualified


# ---------------------------------------------------------------------------
# Coverage sets — methods surfaced by each transport layer
# ---------------------------------------------------------------------------

# REST endpoints in voicetest/rest.py
REST_SURFACED = {
    # Discovery
    "DiscoveryService.list_importers",
    "DiscoveryService.list_export_formats",
    # Agent CRUD
    "AgentService.list_agents",
    "AgentService.get_agent",
    "AgentService.create_agent",
    "AgentService.update_agent",
    "AgentService.delete_agent",
    "AgentService.import_agent",
    "AgentService.export_agent",
    # Agent graph & prompts
    "AgentService.load_graph",
    "AgentService.save_graph",
    "AgentService.get_graph_with_etag",
    "AgentService.get_variables",
    "AgentService.update_prompt",
    "AgentService.update_metadata",
    # Metrics config
    "AgentService.get_metrics_config",
    "AgentService.update_metrics_config",
    # Test cases
    "TestCaseService.list_tests",
    "TestCaseService.create_test",
    "TestCaseService.update_test",
    "TestCaseService.delete_test",
    "TestCaseService.get_test",
    "TestCaseService.link_test_file",
    "TestCaseService.unlink_test_file",
    "TestCaseService.export_tests",
    # Test execution
    "TestExecutionService.run_test",
    "TestExecutionService.run_tests",
    "TestExecutionService.evaluate_global_metrics",
    # Evaluation
    "EvaluationService.evaluate_transcript",
    "EvaluationService.audio_eval_result",
    # Decompose
    "DecomposeService.decompose",
    # Diagnosis
    "DiagnosisService.diagnose_failure",
    "DiagnosisService.apply_and_rerun",
    "DiagnosisService.revise_fix",
    # Snippets
    "SnippetService.get_snippets",
    "SnippetService.update_all_snippets",
    "SnippetService.update_snippet",
    "SnippetService.delete_snippet",
    "SnippetService.analyze_dry",
    "SnippetService.apply_snippets",
    # Runs
    "RunService.create_run",
    "RunService.list_runs",
    "RunService.get_run",
    "RunService.delete_run",
    # Platforms
    "PlatformService.list_platforms",
    "PlatformService.get_status",
    "PlatformService.configure",
    "PlatformService.list_remote_agents",
    "PlatformService.import_from_platform",
    "PlatformService.export_to_platform",
    "PlatformService.get_sync_status",
    "PlatformService.sync_to_platform",
    # Settings
    "SettingsService.get_settings",
    "SettingsService.update_settings",
    "SettingsService.get_defaults",
}

# CLI commands in voicetest/cli.py
CLI_SURFACED = {
    # Agent CRUD + graph
    "AgentService.import_agent",
    "AgentService.export_agent",
    "AgentService.create_agent",
    "AgentService.list_agents",
    "AgentService.get_agent",
    "AgentService.update_agent",
    "AgentService.delete_agent",
    "AgentService.load_graph",
    "AgentService.save_graph",
    # Discovery
    "DiscoveryService.list_importers",
    "DiscoveryService.list_export_formats",
    # Test case CRUD
    "TestCaseService.create_test",
    "TestCaseService.list_tests",
    "TestCaseService.get_test",
    "TestCaseService.update_test",
    "TestCaseService.delete_test",
    "TestCaseService.link_test_file",
    "TestCaseService.unlink_test_file",
    "TestCaseService.export_tests",
    # Test execution
    "TestExecutionService.run_test",
    "TestExecutionService.run_tests",
    # Run history
    "RunService.create_run",
    "RunService.add_result",
    "RunService.list_runs",
    "RunService.get_run",
    "RunService.delete_run",
    # Snippets
    "SnippetService.get_snippets",
    "SnippetService.update_all_snippets",
    "SnippetService.update_snippet",
    "SnippetService.delete_snippet",
    "SnippetService.analyze_dry",
    "SnippetService.apply_snippets",
    # Settings
    "SettingsService.get_settings",
    "SettingsService.update_settings",
    "SettingsService.get_defaults",
    # Platforms
    "PlatformService.list_platforms",
    "PlatformService.get_status",
    "PlatformService.configure",
    "PlatformService.list_remote_agents",
    "PlatformService.import_from_platform",
    "PlatformService.export_to_platform",
    # Evaluation
    "EvaluationService.evaluate_transcript",
    # Decompose
    "DecomposeService.decompose",
    # Diagnosis
    "DiagnosisService.diagnose_failure",
    "DiagnosisService.apply_and_rerun",
    "DiagnosisService.revise_fix",
}

# TUI shell commands in voicetest/tui/shell.py
TUI_SURFACED = {
    "AgentService.import_agent",
    "AgentService.export_agent",
    "DiscoveryService.list_importers",
    "DiscoveryService.list_export_formats",
    "SettingsService.update_settings",
    "TestExecutionService.run_test",
    "TestExecutionService.run_tests",
}

# Methods that intentionally have no direct transport surface.
# Each MUST have a justification explaining why.
INTERNAL_ONLY = {
    # RunService — orchestration helpers called by _execute_run / background tasks
    "RunService.create_pending_result": "Called by REST _execute_run background task",
    "RunService.complete_result": "Called by REST _execute_run background task",
    "RunService.mark_result_error": "Called by REST _execute_run background task",
    "RunService.mark_result_cancelled": "Called by REST _execute_run background task",
    "RunService.complete": "Called by REST _execute_run background task",
    "RunService.update_transcript": "Called by call WebSocket handler",
    "RunService.update_audio_eval": "Called by REST audio_eval_result handler",
    "RunService.add_result_from_call": "Called by REST _save_call_as_run handler",
    # DecomposeService — helpers called by decompose pipeline
    "DecomposeService.build_sub_graph": "Called by decompose internally for each sub-agent",
    "DecomposeService.build_manifest": "Called by decompose internally to build manifest",
    # DiagnosisService — helpers called by other diagnosis methods
    "DiagnosisService.apply_fix_to_graph": "Called by apply_and_rerun and save-fix handler",
    "DiagnosisService.scores_improved": "Called by apply_and_rerun internally",
    # TestCaseService — internal helpers
    "TestCaseService.to_model": "Type conversion helper, not a user operation",
    "TestCaseService.find_linked_test": "Internal lookup used by other service methods",
    "TestCaseService.load_test_cases": "File loading helper for CLI/TUI runners",
    # EvaluationService — called internally by test execution
    "EvaluationService.evaluate_global_metrics": "Called by TestExecutionService.run_test",
    # DiscoveryService — REST-only, no CLI/TUI needed
    "DiscoveryService.list_platforms": "REST-only (platforms are a web UI feature)",
}

# REST methods intentionally not in the CLI, with justifications.
CLI_EXCLUDED_FROM_REST = {
    "AgentService.get_graph_with_etag": "HTTP caching optimization (ETag), not relevant for CLI",
    "AgentService.get_variables": "Web UI helper for variable picker, CLI uses file-based workflow",
    "AgentService.update_prompt": "Web UI inline edit, CLI edits files directly",
    "AgentService.update_metadata": "Web UI inline edit, CLI edits files directly",
    "AgentService.get_metrics_config": "Web UI metrics panel, CLI uses file-based workflow",
    "AgentService.update_metrics_config": "Web UI metrics panel, CLI uses file-based workflow",
    "EvaluationService.audio_eval_result": "Audio pipeline callback, not a user operation",
    "PlatformService.get_sync_status": "Web UI sync indicator, CLI uses explicit push/import",
    "PlatformService.sync_to_platform": "Web UI one-click sync, CLI uses explicit push",
    "TestExecutionService.evaluate_global_metrics": (
        "Called internally by run_test, not a standalone operation"
    ),
}

# Combined set of all accounted-for methods
ALL_SURFACED = REST_SURFACED | CLI_SURFACED | TUI_SURFACED | set(INTERNAL_ONLY.keys())


class TestSurfaceCoverage:
    """Every public service method must be surfaced or explicitly internal."""

    def test_all_methods_accounted_for(self):
        """Fails when a new service method exists that is not in any coverage set."""
        discovered = _all_qualified()
        uncovered = discovered - ALL_SURFACED
        assert not uncovered, (
            "Service method(s) not surfaced by any transport or listed in INTERNAL_ONLY:\n"
            + "\n".join(f"  - {m}" for m in sorted(uncovered))
            + "\n\nAdd to a transport coverage set or to INTERNAL_ONLY with a justification."
        )

    def test_no_stale_coverage_entries(self):
        """Fails when a coverage set references a method that no longer exists."""
        discovered = _all_qualified()
        for label, coverage_set in [
            ("REST_SURFACED", REST_SURFACED),
            ("CLI_SURFACED", CLI_SURFACED),
            ("TUI_SURFACED", TUI_SURFACED),
        ]:
            stale = coverage_set - discovered
            assert not stale, f"Stale entries in {label} (methods no longer exist):\n" + "\n".join(
                f"  - {m}" for m in sorted(stale)
            )

    def test_no_stale_internal_entries(self):
        """Fails when INTERNAL_ONLY references a method that no longer exists."""
        discovered = _all_qualified()
        stale = set(INTERNAL_ONLY.keys()) - discovered
        assert not stale, "Stale entries in INTERNAL_ONLY (methods no longer exist):\n" + "\n".join(
            f"  - {m}" for m in sorted(stale)
        )

    def test_internal_entries_have_justifications(self):
        """Every INTERNAL_ONLY entry must have a non-empty justification string."""
        for key, reason in INTERNAL_ONLY.items():
            assert reason and reason.strip(), f"INTERNAL_ONLY['{key}'] has no justification"

    def test_no_double_accounting(self):
        """Warn if a method is in INTERNAL_ONLY but also in a transport set."""
        internal_keys = set(INTERNAL_ONLY.keys())
        surfaced = REST_SURFACED | CLI_SURFACED | TUI_SURFACED
        overlap = internal_keys & surfaced
        # Overlap is allowed for methods that are both called internally AND
        # exposed via a transport (e.g., evaluate_global_metrics). But flag
        # it so the team is aware.
        if overlap:
            pytest.skip(
                "Methods in both INTERNAL_ONLY and a transport set (review if intentional):\n"
                + "\n".join(f"  - {m}" for m in sorted(overlap))
            )

    def test_cli_covers_rest_endpoints(self):
        """Every REST-surfaced method should also be CLI-surfaced, unless excluded."""
        rest_only = REST_SURFACED - CLI_SURFACED - set(CLI_EXCLUDED_FROM_REST.keys())
        assert not rest_only, (
            "REST method(s) not in CLI_SURFACED or CLI_EXCLUDED_FROM_REST:\n"
            + "\n".join(f"  - {m}" for m in sorted(rest_only))
            + "\n\nAdd to CLI_SURFACED (implement in CLI) or "
            "CLI_EXCLUDED_FROM_REST with a justification."
        )

    def test_cli_excluded_entries_have_justifications(self):
        """Every CLI_EXCLUDED_FROM_REST entry must have a non-empty justification."""
        for key, reason in CLI_EXCLUDED_FROM_REST.items():
            assert reason and reason.strip(), (
                f"CLI_EXCLUDED_FROM_REST['{key}'] has no justification"
            )

    def test_cli_excluded_entries_are_in_rest(self):
        """CLI_EXCLUDED_FROM_REST entries must actually be REST-only methods."""
        for key in CLI_EXCLUDED_FROM_REST:
            assert key in REST_SURFACED, (
                f"CLI_EXCLUDED_FROM_REST['{key}'] is not in REST_SURFACED — remove it"
            )
            assert key not in CLI_SURFACED, (
                f"CLI_EXCLUDED_FROM_REST['{key}'] is in CLI_SURFACED — remove from exclusion list"
            )

    def test_discovery_finds_services(self):
        """Sanity check: AST scanner finds the expected service classes."""
        services = _discover_service_methods()
        expected = {
            "AgentService",
            "DecomposeService",
            "DiagnosisService",
            "DiscoveryService",
            "EvaluationService",
            "PlatformService",
            "RunService",
            "SettingsService",
            "SnippetService",
            "TestCaseService",
            "TestExecutionService",
        }
        assert set(services.keys()) == expected
