"""Application services bag for CLI/TUI shells.

CLI and TUI command code receives an `AppServices` instance from the composition
root. REST endpoints don't use this bag — they resolve services per-request from
`request.app.state.container`.
"""

from dataclasses import dataclass

import punq

from voicetest.services.agents import AgentService
from voicetest.services.decompose import DecomposeService
from voicetest.services.diagnosis import DiagnosisService
from voicetest.services.discovery import DiscoveryService
from voicetest.services.evaluation import EvaluationService
from voicetest.services.platforms import PlatformService
from voicetest.services.runs import RunService
from voicetest.services.settings import SettingsService
from voicetest.services.snippets import SnippetService
from voicetest.services.testing import TestCaseService
from voicetest.services.testing import TestExecutionService


@dataclass(frozen=True)
class AppServices:
    """Application services resolved from the DI container."""

    agents: AgentService
    decompose: DecomposeService
    diagnosis: DiagnosisService
    discovery: DiscoveryService
    eval: EvaluationService
    platforms: PlatformService
    runs: RunService
    settings: SettingsService
    snippets: SnippetService
    test_cases: TestCaseService
    test_execution: TestExecutionService


def build_app_services(container: punq.Container) -> AppServices:
    """Resolve every application service from the container into a typed bag."""
    return AppServices(
        agents=container.resolve(AgentService),
        decompose=container.resolve(DecomposeService),
        diagnosis=container.resolve(DiagnosisService),
        discovery=container.resolve(DiscoveryService),
        eval=container.resolve(EvaluationService),
        platforms=container.resolve(PlatformService),
        runs=container.resolve(RunService),
        settings=container.resolve(SettingsService),
        snippets=container.resolve(SnippetService),
        test_cases=container.resolve(TestCaseService),
        test_execution=container.resolve(TestExecutionService),
    )
