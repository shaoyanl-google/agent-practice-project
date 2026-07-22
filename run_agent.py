import asyncio
import os
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Load environment variables from the agent's .env file
agent_dir = os.path.join(os.path.dirname(__file__), "chore_planning_agent")
load_dotenv(os.path.join(agent_dir, ".env"))

# Import the root agent defined in the skeleton project
from chore_planning_agent.agent import root_agent

async def main():
    # 1. Check if the API key is set
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        print("WARNING: GOOGLE_API_KEY is not set or is using the placeholder value.")
        print("Please edit the 'chore_planning_agent/.env' file and configure a valid Gemini API key from AI Studio.")
        print("You can get a free key from: https://aistudio.google.com/apikey\n")
        return

    # 2. Instantiate the Runner with our agent and an in-memory session service
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="chore_planning_agent", session_service=session_service)
    
    # 3. Initialize a session
    user_id = "default_user"
    session_id = "default_session"
    
    await session_service.create_session(
        user_id=user_id,
        session_id=session_id,
        app_name="chore_planning_agent",
    )
    
    # 4. Prompt the user for input and run the agent
    print("Agent is ready! Type your message below (type 'exit' or press Ctrl+C to quit):\n")
    
    while True:
        try:
            query = input("User: ")
            if not query or not query.strip():
                continue
            if query.lower() in ("exit", "quit"):
                print("Goodbye!")
                break
                
            new_message = types.Content(role='user', parts=[types.Part(text=query)])
            print("Agent: ", end="", flush=True)
            
            # 5. Stream responses from the agent
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
            
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

if __name__ == "__main__":
    asyncio.run(main())
