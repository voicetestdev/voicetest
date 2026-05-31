"""Evaluation service: evaluate transcripts against metrics."""

from voicetest.judges.metric import MetricJudge
from voicetest.judges.rule import RuleJudge
from voicetest.models.agent import MetricsConfig
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.test_case import TestCase
from voicetest.services.settings import SettingsService
from voicetest.services.testing.execution import TestExecutionService
from voicetest.settings import resolve_model
from voicetest.util.audio import AudioRoundTrip


class EvaluationService:
    """Evaluates transcripts against metrics. Stateless."""

    def __init__(
        self,
        test_execution_service: TestExecutionService,
        settings_service: SettingsService,
    ):
        self._execution = test_execution_service
        self._settings = settings_service

    async def evaluate_transcript(
        self,
        transcript: list[Message],
        metrics: list[str],
        judge_model: str | None = None,
        _mock_mode: bool = False,
    ) -> list[MetricResult]:
        """Evaluate an existing transcript against metrics (no simulation)."""
        if judge_model is None:
            judge_model = resolve_model(self._settings.get_settings().models.judge)
        judge = MetricJudge(judge_model)

        if _mock_mode:
            judge._mock_mode = True
            judge._mock_results = [
                MetricResult(metric=m, passed=True, reasoning="Mock evaluation", confidence=0.9)
                for m in metrics
            ]

        return await judge.evaluate_all(transcript, metrics)

    async def audio_eval_result(
        self,
        transcript: list[Message],
        test_case: TestCase,
        metrics_config: MetricsConfig | None = None,
        judge_model: str | None = None,
    ) -> tuple[list[Message], list[MetricResult]]:
        """Run audio evaluation on an existing transcript.

        Performs TTS->STT round-trip on assistant messages and re-evaluates
        metrics using the "heard" text."""
        settings = self._settings.get_settings()

        audio_rt = AudioRoundTrip.from_settings(settings)
        transformed = await audio_rt.transform_transcript(transcript)

        judge_model = judge_model or resolve_model(settings.models.judge)
        test_type = test_case.effective_type

        threshold = metrics_config.threshold if metrics_config else 0.7

        if test_type == "rule":
            rule_judge = RuleJudge(pattern_engine=settings.run.pattern_engine)
            audio_metrics = await rule_judge.evaluate(
                transformed,
                test_case.includes,
                test_case.excludes,
                test_case.patterns,
                use_heard=True,
            )
        else:
            metric_judge = MetricJudge(judge_model)
            audio_metrics = await metric_judge.evaluate_all(
                transformed,
                test_case.metrics,
                threshold=threshold,
                use_heard=True,
            )

        if metrics_config:
            global_results = await self._execution.evaluate_global_metrics(
                transformed,
                metrics_config,
                judge_model=judge_model,
                use_heard=True,
            )
            audio_metrics.extend(global_results)

        await audio_rt.close()
        return transformed, audio_metrics
