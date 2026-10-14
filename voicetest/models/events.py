"""Provider-neutral conversation events for structured judge input."""

from typing import TYPE_CHECKING
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import SerializerFunctionWrapHandler
from pydantic import model_serializer
from pydantic import model_validator


if TYPE_CHECKING:
    from voicetest.models.results import Message


EventKind = Literal["speech", "keypad_input", "tool_call", "tool_result", "transition"]

JUDGE_INPUT_TRANSCRIPT = "transcript"
JUDGE_INPUT_EVENTS = "events"

JudgeInput = Literal[JUDGE_INPUT_TRANSCRIPT, JUDGE_INPUT_EVENTS]

ROUTE_TOOL_PREFIX = "route_to_"
EXTRACT_TOOL_NAME = "extract_variables"


class JudgeEvent(BaseModel):
    """A provider-neutral event in the conversation timeline."""

    kind: EventKind = Field(description="Event kind, independent of speaker")
    speaker: str | None = None
    start_offset_ms: int | None = Field(
        default=None, ge=0, description="Offset from conversation start"
    )
    end_offset_ms: int | None = Field(
        default=None, ge=0, description="Offset from conversation start, when available"
    )
    content: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_offsets(self) -> "JudgeEvent":
        if (
            self.start_offset_ms is not None
            and self.end_offset_ms is not None
            and self.end_offset_ms < self.start_offset_ms
        ):
            raise ValueError("end_offset_ms must not precede start_offset_ms")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None and v != {}}


def order_events(events: list[JudgeEvent]) -> list[JudgeEvent]:
    """Stable chronological order; an untimed event stays after its predecessor."""
    keyed: list[tuple[int, int, JudgeEvent]] = []
    anchor = -1
    for index, event in enumerate(events):
        if event.start_offset_ms is not None:
            anchor = event.start_offset_ms
        keyed.append((anchor, index, event))
    keyed.sort(key=lambda item: (item[0], item[1]))
    return [event for _, _, event in keyed]


def events_from_messages(messages: list["Message"], use_heard: bool = False) -> list[JudgeEvent]:
    """Convert a voicetest transcript into judge events."""
    timestamps = [m.timestamp for m in messages if m.timestamp is not None]
    origin = min(timestamps) if timestamps else None

    events: list[JudgeEvent] = []
    for message in messages:
        offset = None
        if origin is not None and message.timestamp is not None:
            offset = int((message.timestamp - origin).total_seconds() * 1000)

        if message.role in ("user", "assistant"):
            events.append(_speech_event(message, offset, use_heard))
        elif message.role == "tool":
            events.extend(_tool_events(message, offset))
    return events


def _speech_event(message: "Message", offset: int | None, use_heard: bool) -> JudgeEvent:
    audio = message.audio()
    content = message.content
    metadata: dict[str, Any] = {}
    if use_heard and message.role == "assistant" and audio.heard is not None:
        content = audio.heard
        metadata["intended"] = message.content
    if audio.latency_ms is not None:
        metadata["latency_ms"] = audio.latency_ms
    return JudgeEvent(
        kind="speech",
        speaker=message.role,
        start_offset_ms=offset,
        content=content,
        metadata=metadata,
    )


def _tool_events(message: "Message", offset: int | None) -> list[JudgeEvent]:
    metadata = dict(message.metadata)
    tool_name = metadata.pop("tool_name", None)

    if tool_name and tool_name.startswith(ROUTE_TOOL_PREFIX):
        to_node = metadata.pop("node_id", tool_name.removeprefix(ROUTE_TOOL_PREFIX))
        return [
            JudgeEvent(
                kind="transition",
                start_offset_ms=offset,
                content=message.content,
                payload={"to_node": to_node},
                metadata=metadata,
            )
        ]

    if tool_name == EXTRACT_TOOL_NAME:
        extracted = metadata.pop("extracted", {})
        return [
            JudgeEvent(
                kind="tool_call",
                start_offset_ms=offset,
                payload={"name": tool_name},
                metadata=metadata,
            ),
            JudgeEvent(
                kind="tool_result",
                start_offset_ms=offset,
                content=message.content,
                payload={"name": tool_name, "result": extracted},
                metadata=metadata,
            ),
        ]

    return [
        JudgeEvent(
            kind="tool_call",
            start_offset_ms=offset,
            content=message.content,
            payload={"name": tool_name} if tool_name else {},
            metadata=metadata,
        )
    ]
