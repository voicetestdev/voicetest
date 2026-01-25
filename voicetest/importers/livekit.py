"""LiveKit Python agent file importer.

Parses Python agent files using AST to extract AgentGraph structure.
"""

import ast
from pathlib import Path
from typing import Any

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
    Transition,
    TransitionCondition,
)


class LiveKitImporter:
    """Import LiveKit Python agent files via AST parsing."""

    @property
    def source_type(self) -> str:
        return "livekit"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="livekit",
            description="Import LiveKit Python agent files",
            file_patterns=["*.py"],
        )

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Detect LiveKit agent Python files.

        Looks for:
        - from livekit.agents import Agent
        - class definitions that inherit from Agent
        """
        if isinstance(path_or_config, dict):
            return self._can_import_dict(path_or_config)

        try:
            path = Path(path_or_config)
            if path.suffix != ".py":
                return False

            content = path.read_text()
            return self._looks_like_livekit_agent(content)
        except Exception:
            return False

    def _can_import_dict(self, config: dict) -> bool:
        """Check if dict looks like a LiveKit agent config."""
        if "code" in config:
            return self._looks_like_livekit_agent(config["code"])
        return False

    def _looks_like_livekit_agent(self, content: str) -> bool:
        """Check if Python content looks like a LiveKit agent."""
        has_import = (
            "from livekit.agents import" in content
            or "from livekit import agents" in content
            or "import livekit.agents" in content
        )

        has_agent_class = "class " in content and "(Agent)" in content

        return has_import or has_agent_class

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert LiveKit Python agent to AgentGraph."""
        if isinstance(path_or_config, dict):
            content = path_or_config.get("code", "")
            if not content:
                raise ValueError("Dict config must contain 'code' field")
        else:
            path = Path(path_or_config)
            content = path.read_text()

        return self._parse_agent_code(content)

    def _parse_agent_code(self, content: str) -> AgentGraph:
        """Parse Python code to extract AgentGraph."""
        tree = ast.parse(content)

        nodes: dict[str, AgentNode] = {}
        entry_node_id: str | None = None

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and self._is_agent_class(node):
                agent_node = self._parse_agent_class(node)
                nodes[agent_node.id] = agent_node
                if entry_node_id is None:
                    entry_node_id = agent_node.id

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_entry_agent":
                entry_agent = self._extract_entry_agent(node)
                if entry_agent:
                    entry_node_id = entry_agent

        if not nodes:
            nodes["main"] = AgentNode(
                id="main",
                instructions="LiveKit agent (no agent classes found)",
                tools=[],
                transitions=[],
                metadata={"livekit_raw": True},
            )
            entry_node_id = "main"

        return AgentGraph(
            nodes=nodes,
            entry_node_id=entry_node_id or list(nodes.keys())[0],
            source_type="livekit",
            source_metadata={"original_code_hash": hash(content)},
        )

    def _is_agent_class(self, class_def: ast.ClassDef) -> bool:
        """Check if a class inherits from Agent."""
        for base in class_def.bases:
            if isinstance(base, ast.Name) and base.id == "Agent":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "Agent":
                return True
        return False

    def _parse_agent_class(self, class_def: ast.ClassDef) -> AgentNode:
        """Parse an agent class to extract AgentNode."""
        node_id = class_def.name
        if node_id.startswith("Agent_"):
            node_id = node_id[6:]

        instructions = ""
        tools: list[ToolDefinition] = []
        transitions: list[Transition] = []

        for item in class_def.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                if item.name == "__init__":
                    instructions = self._extract_instructions(item)
                elif self._is_function_tool(item):
                    tool, transition = self._parse_function_tool(item)
                    if tool:
                        tools.append(tool)
                    if transition:
                        transitions.append(transition)

        return AgentNode(
            id=node_id,
            instructions=instructions,
            tools=tools,
            transitions=transitions,
            metadata={"livekit_class": class_def.name},
        )

    def _extract_instructions(self, init_method: ast.FunctionDef) -> str:
        """Extract instructions from __init__ method's super().__init__(instructions=...)."""
        for stmt in ast.walk(init_method):
            if isinstance(stmt, ast.Call) and self._is_super_init_call(stmt):
                for keyword in stmt.keywords:
                    if keyword.arg == "instructions":
                        return self._extract_string_value(keyword.value)
        return ""

    def _is_super_init_call(self, call: ast.Call) -> bool:
        """Check if call is super().__init__(...)."""
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "__init__"):
            return False
        if not isinstance(call.func.value, ast.Call):
            return False
        func = call.func.value.func
        return isinstance(func, ast.Name) and func.id == "super"

    def _extract_string_value(self, node: ast.expr) -> str:
        """Extract string value from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
            return "".join(parts)
        return ""

    def _is_function_tool(self, func_def: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if function has @function_tool decorator."""
        for decorator in func_def.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "function_tool":
                return True
            if isinstance(decorator, ast.Attribute) and decorator.attr == "function_tool":
                return True
        return False

    def _parse_function_tool(
        self, func_def: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> tuple[ToolDefinition | None, Transition | None]:
        """Parse a @function_tool decorated method.

        Returns:
            Tuple of (tool_definition, transition_if_any).
        """
        docstring = ast.get_docstring(func_def) or ""

        returns_agent = self._returns_agent_instance(func_def)
        target_node_id = None

        if returns_agent:
            target_node_id = self._extract_return_agent_class(func_def)

        tool = ToolDefinition(
            name=func_def.name,
            description=docstring,
            parameters=self._extract_parameters(func_def),
            type="function_tool",
        )

        transition = None
        if target_node_id:
            condition_value = docstring or f"Route to {target_node_id}"
            transition = Transition(
                target_node_id=target_node_id,
                condition=TransitionCondition(
                    type="tool_call",
                    value=condition_value,
                ),
                description=f"Transition via {func_def.name}",
            )

        return tool, transition

    def _returns_agent_instance(self, func_def: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if function returns an Agent instance."""
        for stmt in ast.walk(func_def):
            if isinstance(stmt, ast.Return) and stmt.value:
                if isinstance(stmt.value, ast.Tuple) and stmt.value.elts:
                    first_elem = stmt.value.elts[0]
                    if self._is_agent_instantiation(first_elem):
                        return True
                elif self._is_agent_instantiation(stmt.value):
                    return True
        return False

    def _is_agent_instantiation(self, node: ast.expr) -> bool:
        """Check if node is an Agent class instantiation."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id.startswith("Agent_") or node.func.id == "Agent"
            if isinstance(node.func, ast.Attribute):
                return node.func.attr.startswith("Agent_")
        return False

    def _extract_return_agent_class(
        self, func_def: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> str | None:
        """Extract the agent class name from a return statement."""
        for stmt in ast.walk(func_def):
            if isinstance(stmt, ast.Return) and stmt.value:
                if isinstance(stmt.value, ast.Tuple) and stmt.value.elts:
                    first_elem = stmt.value.elts[0]
                    class_name = self._get_class_name(first_elem)
                    if class_name:
                        if class_name.startswith("Agent_"):
                            return class_name[6:]
                        return class_name
                else:
                    class_name = self._get_class_name(stmt.value)
                    if class_name:
                        if class_name.startswith("Agent_"):
                            return class_name[6:]
                        return class_name
        return None

    def _get_class_name(self, node: ast.expr) -> str | None:
        """Get class name from instantiation call."""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            if isinstance(node.func, ast.Attribute):
                return node.func.attr
        return None

    def _extract_parameters(
        self, func_def: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> dict[str, Any]:
        """Extract function parameters as JSON schema."""
        params: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for arg in func_def.args.args:
            if arg.arg in ("self", "ctx"):
                continue

            param_type = "string"
            if arg.annotation:
                param_type = self._annotation_to_type(arg.annotation)

            params["properties"][arg.arg] = {"type": param_type}
            params["required"].append(arg.arg)

        if func_def.args.defaults:
            num_defaults = len(func_def.args.defaults)
            num_args = len(func_def.args.args)
            for i in range(num_defaults):
                arg_index = num_args - num_defaults + i
                if arg_index >= 0:
                    arg_name = func_def.args.args[arg_index].arg
                    if arg_name in params["required"]:
                        params["required"].remove(arg_name)

        return params

    def _annotation_to_type(self, annotation: ast.expr) -> str:
        """Convert Python type annotation to JSON schema type."""
        if isinstance(annotation, ast.Name):
            type_map = {
                "str": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "list": "array",
                "dict": "object",
            }
            return type_map.get(annotation.id, "string")
        return "string"

    def _extract_entry_agent(self, func_def: ast.FunctionDef) -> str | None:
        """Extract entry agent from get_entry_agent function."""
        for stmt in ast.walk(func_def):
            if isinstance(stmt, ast.Return) and stmt.value:
                class_name = self._get_class_name(stmt.value)
                if class_name:
                    if class_name.startswith("Agent_"):
                        return class_name[6:]
                    return class_name
        return None
