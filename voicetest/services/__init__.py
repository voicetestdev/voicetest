"""Service layer for voicetest.

Services own all business logic. CLI and REST are pure transport adapters
that resolve services from the DI container.
"""

from voicetest.container import get_container
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


def get_discovery_service() -> DiscoveryService:
    return get_container().resolve(DiscoveryService)


def get_agent_service() -> AgentService:
    return get_container().resolve(AgentService)


def get_test_case_service() -> TestCaseService:
    return get_container().resolve(TestCaseService)


def get_test_execution_service() -> TestExecutionService:
    return get_container().resolve(TestExecutionService)


def get_evaluation_service() -> EvaluationService:
    return get_container().resolve(EvaluationService)


def get_decompose_service() -> DecomposeService:
    return get_container().resolve(DecomposeService)


def get_diagnosis_service() -> DiagnosisService:
    return get_container().resolve(DiagnosisService)


def get_snippet_service() -> SnippetService:
    return get_container().resolve(SnippetService)


def get_run_service() -> RunService:
    return get_container().resolve(RunService)


def get_platform_service() -> PlatformService:
    return get_container().resolve(PlatformService)


def get_settings_service() -> SettingsService:
    return get_container().resolve(SettingsService)


__all__ = [
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
    "get_agent_service",
    "get_decompose_service",
    "get_diagnosis_service",
    "get_discovery_service",
    "get_evaluation_service",
    "get_platform_service",
    "get_run_service",
    "get_settings_service",
    "get_snippet_service",
    "get_test_case_service",
    "get_test_execution_service",
]
