"""Tests for voicetest.models.events module."""

from datetime import datetime
from datetime import timedelta

from pydantic import ValidationError
import pytest

from voicetest.models.events import JudgeEvent
from voicetest.models.events import events_from_messages
from voicetest.models.events import order_events
from voicetest.models.results import AudioMetadata
from voicetest.models.results import Message


class TestJudgeEvent:
    """Tests for JudgeEvent model."""

    def test_keypad_event_carries_digits_in_payload(self):
        event = JudgeEvent(kind="keypad_input", speaker="user", payload={"digits": "1"})

        assert event.kind == "keypad_input"
        assert event.payload == {"digits": "1"}
        assert event.start_offset_ms is None
        assert event.end_offset_ms is None

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValidationError):
            JudgeEvent(kind="other")

    def test_rejects_negative_offset(self):
        with pytest.raises(ValidationError):
            JudgeEvent(kind="speech", start_offset_ms=-1)

    def test_rejects_end_before_start(self):
        with pytest.raises(ValidationError):
            JudgeEvent(kind="speech", start_offset_ms=500, end_offset_ms=100)

    def test_allows_end_without_start(self):
        event = JudgeEvent(kind="speech", end_offset_ms=100)

        assert event.end_offset_ms == 100

    def test_dump_omits_missing_timing_and_empty_fields(self):
        event = JudgeEvent(kind="speech", speaker="user", content="hi")

        assert event.model_dump() == {"kind": "speech", "speaker": "user", "content": "hi"}

    def test_dump_round_trips(self):
        event = JudgeEvent(
            kind="tool_call",
            start_offset_ms=1200,
            payload={"name": "lookup"},
            metadata={"source": "retell"},
        )

        assert JudgeEvent.model_validate(event.model_dump()) == event


class TestOrderEvents:
    """Tests for order_events."""

    def test_sorts_by_start_offset(self):
        late = JudgeEvent(kind="speech", content="late", start_offset_ms=2000)
        early = JudgeEvent(kind="speech", content="early", start_offset_ms=100)

        assert order_events([late, early]) == [early, late]

    def test_equal_offsets_keep_input_order(self):
        a = JudgeEvent(kind="tool_call", content="a", start_offset_ms=100)
        b = JudgeEvent(kind="tool_result", content="b", start_offset_ms=100)

        assert order_events([a, b]) == [a, b]

    def test_all_untimed_keep_input_order(self):
        events = [JudgeEvent(kind="speech", content=str(i)) for i in range(5)]

        assert order_events(events) == events

    def test_untimed_event_stays_after_its_predecessor(self):
        first = JudgeEvent(kind="speech", content="first", start_offset_ms=3000)
        untimed = JudgeEvent(kind="keypad_input", payload={"digits": "1"})
        earlier = JudgeEvent(kind="speech", content="earlier", start_offset_ms=1000)

        assert order_events([first, untimed, earlier]) == [earlier, first, untimed]

    def test_leading_untimed_event_stays_first(self):
        untimed = JudgeEvent(kind="speech", content="untimed")
        timed = JudgeEvent(kind="speech", content="timed", start_offset_ms=0)

        assert order_events([untimed, timed]) == [untimed, timed]

    def test_does_not_fill_missing_offsets(self):
        timed = JudgeEvent(kind="speech", start_offset_ms=1000)
        untimed = JudgeEvent(kind="speech")

        ordered = order_events([timed, untimed])

        assert ordered[1].start_offset_ms is None


class TestEventsFromMessages:
    """Tests for events_from_messages."""

    def test_user_and_assistant_become_speech(self):
        messages = [
            Message(role="assistant", content="Hello"),
            Message(role="user", content="Hi"),
        ]

        events = events_from_messages(messages)

        assert events == [
            JudgeEvent(kind="speech", speaker="assistant", content="Hello"),
            JudgeEvent(kind="speech", speaker="user", content="Hi"),
        ]

    def test_route_tool_message_becomes_transition(self):
        message = Message(
            role="tool",
            content="Transitioned to billing",
            metadata={"tool_name": "route_to_billing", "node_id": "billing"},
        )

        events = events_from_messages([message])

        assert events == [
            JudgeEvent(
                kind="transition",
                content="Transitioned to billing",
                payload={"to_node": "billing"},
            )
        ]

    def test_extraction_becomes_tool_call_and_result(self):
        message = Message(
            role="tool",
            content="Extracted: name=Ann",
            metadata={
                "tool_name": "extract_variables",
                "node_id": "intake",
                "extracted": {"name": "Ann"},
            },
        )

        events = events_from_messages([message])

        assert events == [
            JudgeEvent(
                kind="tool_call",
                payload={"name": "extract_variables"},
                metadata={"node_id": "intake"},
            ),
            JudgeEvent(
                kind="tool_result",
                content="Extracted: name=Ann",
                payload={"name": "extract_variables", "result": {"name": "Ann"}},
                metadata={"node_id": "intake"},
            ),
        ]

    def test_named_tool_message_is_tool_call(self):
        message = Message(
            role="tool",
            content="Looked up order",
            metadata={"tool_name": "lookup_order", "node_id": "orders"},
        )

        events = events_from_messages([message])

        assert events == [
            JudgeEvent(
                kind="tool_call",
                content="Looked up order",
                payload={"name": "lookup_order"},
                metadata={"node_id": "orders"},
            )
        ]

    def test_unnamed_tool_message_is_tool_call(self):
        message = Message(role="tool", content="did something")

        events = events_from_messages([message])

        assert events == [JudgeEvent(kind="tool_call", content="did something")]

    def test_system_messages_are_not_conversation_events(self):
        messages = [
            Message(role="system", content="You are a helpful agent"),
            Message(role="user", content="Hi"),
        ]

        events = events_from_messages(messages)

        assert events == [JudgeEvent(kind="speech", speaker="user", content="Hi")]

    def test_use_heard_substitutes_assistant_speech(self):
        message = Message(role="assistant", content="intended")
        message.set_audio(AudioMetadata(heard="heard"))

        events = events_from_messages([message], use_heard=True)

        assert events[0].content == "heard"
        assert events[0].metadata["intended"] == "intended"

    def test_use_heard_without_heard_keeps_content(self):
        message = Message(role="assistant", content="intended")

        events = events_from_messages([message], use_heard=True)

        assert events[0].content == "intended"
        assert "intended" not in events[0].metadata

    def test_offsets_relative_to_first_timestamp(self):
        start = datetime(2026, 1, 1, 12, 0, 0)
        messages = [
            Message(role="assistant", content="Hello", timestamp=start),
            Message(role="user", content="Hi", timestamp=start + timedelta(milliseconds=1500)),
        ]

        events = events_from_messages(messages)

        assert [e.start_offset_ms for e in events] == [0, 1500]
        assert [e.end_offset_ms for e in events] == [None, None]

    def test_partial_timestamps_leave_offsets_missing(self):
        start = datetime(2026, 1, 1, 12, 0, 0)
        messages = [
            Message(role="assistant", content="Hello"),
            Message(role="user", content="Hi", timestamp=start),
            Message(role="assistant", content="Bye", timestamp=start + timedelta(seconds=2)),
        ]

        events = events_from_messages(messages)

        assert [e.start_offset_ms for e in events] == [None, 0, 2000]

    def test_latency_is_metadata_not_timing(self):
        message = Message(role="assistant", content="Hello")
        message.set_audio(AudioMetadata(latency_ms=420))

        events = events_from_messages([message])

        assert events[0].start_offset_ms is None
        assert events[0].metadata["latency_ms"] == 420
