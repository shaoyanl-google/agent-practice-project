import asyncio
import os
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Load env variables
agent_dir = os.path.join(os.path.dirname(__file__), "..", "chore_planning_agent")
load_dotenv(os.path.join(agent_dir, ".env"))

from chore_planning_agent.agent import root_agent

async def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY is not set.")
        return

    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="chore_planning_agent", session_service=session_service)
    
    user_id = "test_user"
    session_id = "test_session"
    await session_service.create_session(
        user_id=user_id,
        session_id=session_id,
        app_name="chore_planning_agent"
    )
    
    # We ask to add a chore, but we don't provide Day of Week, Start Time, or Duration.
    query = "I want to add a chore 'Vacuuming'."
    print(f"User: {query}")
    new_message = types.Content(role='user', parts=[types.Part(text=query)])
    
    print("Agent: ", end="", flush=True)
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        if hasattr(event, 'content') and event.content:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
    print("\n")

if __name__ == "__main__":
    asyncio.run(main())
