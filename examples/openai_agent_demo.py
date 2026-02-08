"""
TraceBoard + OpenAI Agents SDK Demo
====================================

Prerequisites:
    pip install traceboard
    export OPENAI_API_KEY=sk-...

Usage:
    python openai_agent_demo.py

Then view traces:
    traceboard ui
"""

import asyncio

import traceboard
traceboard.init()

from agents import Agent, Runner, function_tool


@function_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    weather_data = {
        "tokyo": "Sunny, 22°C",
        "london": "Cloudy, 14°C",
        "new york": "Rainy, 18°C",
        "beijing": "Clear, 25°C",
    }
    return weather_data.get(city.lower(), f"Weather data not available for {city}")


@function_tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error: {e}"


assistant = Agent(
    name="Smart Assistant",
    instructions="""You are a helpful assistant. You can:
    1. Check weather for any city using the get_weather tool
    2. Calculate math expressions using the calculate tool

    Always be helpful and concise in your responses.""",
    tools=[get_weather, calculate],
)


async def main():
    print("=" * 50)
    print("TraceBoard + OpenAI Agents SDK Demo")
    print("=" * 50)
    print()

    print("[Run 1] Simple question...")
    result = await Runner.run(assistant, "What is the weather in Tokyo?")
    print(f"  Response: {result.final_output}")
    print()

    print("[Run 2] Multi-tool question...")
    result = await Runner.run(
        assistant,
        "What's the weather in London? Also, what is 42 * 17 + 3?",
    )
    print(f"  Response: {result.final_output}")
    print()

    print("[Run 3] Follow-up question...")
    result = await Runner.run(assistant, "Calculate 2 ** 10")
    print(f"  Response: {result.final_output}")
    print()

    print("=" * 50)
    print("Done! View traces with: traceboard ui")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
