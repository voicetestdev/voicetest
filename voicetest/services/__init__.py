"""Service layer for voicetest.

Services own all business logic. CLI, TUI, and REST are transport adapters
that receive services from the composition root (entry-point container build).

This package re-exports the service classes for convenience. The `AppServices`
bag (CLI/TUI's typed service container) lives in `app_services.py`.
"""

from voicetest.services.agents import AgentService
from voicetest.services.app_services import AppServices
from voicetest.services.app_services import build_app_services
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


__all__ = [
    "AgentService",
    "AppServices",
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
    "build_app_services",
]
