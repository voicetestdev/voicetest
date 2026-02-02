"""SQLAlchemy ORM models for voicetest storage."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Agent(Base):
    """Agent model representing a voice agent configuration."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)
    graph_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    test_cases: Mapped[list["TestCase"]] = relationship(back_populates="agent")
    runs: Mapped[list["Run"]] = relationship(back_populates="agent")

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "graph_json": self.graph_json,
            "metrics_config": self.metrics_config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TestCase(Base):
    """TestCase model representing a test definition for an agent."""

    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dynamic_variables: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_mocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    type: Mapped[str] = mapped_column(String, default="llm")
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    includes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    excludes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    patterns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    agent: Mapped["Agent"] = relationship(back_populates="test_cases")

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "name": self.name,
            "user_prompt": self.user_prompt,
            "metrics": self.metrics,
            "dynamic_variables": self.dynamic_variables,
            "tool_mocks": self.tool_mocks,
            "type": self.type,
            "llm_model": self.llm_model,
            "includes": self.includes,
            "excludes": self.excludes,
            "patterns": self.patterns,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Run(Base):
    """Run model representing a test execution session."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="runs")
    results: Mapped[list["Result"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Result(Base):
    """Result model representing an individual test result."""

    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    test_case_id: Mapped[str] = mapped_column(String, nullable=False)
    test_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    nodes_visited: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tools_called: Mapped[list | None] = mapped_column(JSON, nullable=True)
    models_used: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    run: Mapped["Run"] = relationship(back_populates="results")

    def to_dict(self) -> dict:
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "test_case_id": self.test_case_id,
            "test_name": self.test_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "turn_count": self.turn_count,
            "end_reason": self.end_reason,
            "error_message": self.error_message,
            "transcript_json": self.transcript_json,
            "metrics_json": self.metrics_json,
            "nodes_visited": self.nodes_visited,
            "tools_called": self.tools_called,
            "models_used": self.models_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
