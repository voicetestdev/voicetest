"""Generated LiveKit agents from voicetest."""

from livekit.agents import Agent
from livekit.agents import RunContext
from livekit.agents import function_tool


class Agent_greeting(Agent):
    """Agent for node: greeting"""

    def __init__(self):
        super().__init__(instructions="""Greet the user warmly and ask how you can help.""")

    @function_tool
    async def route_to_billing(self, ctx: RunContext):
        """User wants to discuss billing or payments."""
        return Agent_billing(), ""

    @function_tool
    async def route_to_support(self, ctx: RunContext):
        """User needs technical support or has a problem."""
        return Agent_support(), ""


class Agent_billing(Agent):
    """Agent for node: billing"""

    def __init__(self):
        super().__init__(
            instructions="""Handle billing inquiries. Help with invoices and payments."""
        )

    @function_tool
    async def route_to_end_call(self, ctx: RunContext):
        """Billing issue resolved, end the call."""
        return Agent_end_call(), ""


class Agent_support(Agent):
    """Agent for node: support"""

    def __init__(self):
        super().__init__(instructions="""Provide technical support. Troubleshoot issues.""")

    @function_tool
    async def route_to_end_call(self, ctx: RunContext):
        """Support issue resolved, end the call."""
        return Agent_end_call(), ""


class Agent_end_call(Agent):
    """Agent for node: end_call"""

    def __init__(self):
        super().__init__(instructions="""Thank the user and end the call politely.""")


# Entry point: greeting
def get_entry_agent():
    return Agent_greeting()
