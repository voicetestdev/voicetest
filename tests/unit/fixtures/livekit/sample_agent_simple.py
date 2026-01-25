"""Simple single-agent LiveKit example."""

from livekit.agents import Agent, RunContext, function_tool


class GreetingAgent(Agent):
    """A simple greeting agent."""

    def __init__(self):
        super().__init__(
            instructions="""You are a friendly assistant. Greet users and help them."""
        )

    @function_tool
    async def get_weather(self, ctx: RunContext, city: str):
        """Get weather for a city."""
        return f"Weather in {city}: Sunny, 72F"


def get_entry_agent():
    return GreetingAgent()
