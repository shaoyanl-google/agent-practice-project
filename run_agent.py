import asyncio
import os
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.runners import Runner
from google.adk.apps import App
from google.adk.apps._configs import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import LLMRegistry
from google.genai import types
from chore_planning_agent.session_store import FileSessionService
from chore_planning_agent.logger import StructuredLogger

logger = StructuredLogger(service_name="chore-planning-agent.runner")

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

    # 2. Instantiate FileSessionService (NoSQL Document Store) and Event Compaction Config
    session_service = FileSessionService(storage_dir="sessions")
    
    # Configure event/history compaction to summarize conversation memory
    llm = LLMRegistry.new_llm('gemini-3.5-flash')
    summarizer = LlmEventSummarizer(llm=llm)
    events_compaction_config = EventsCompactionConfig(
        summarizer=summarizer,
        compaction_interval=3,  # Run compaction every 3 new user messages
        overlap_size=1,         # Retain 1 overlap message
    )
    
    # Build ADK App container
    app = App(
        name="chore_planning_agent",
        root_agent=root_agent,
        events_compaction_config=events_compaction_config
    )
    
    # Instantiate the Runner with our App
    runner = Runner(app=app, session_service=session_service)
    
    # 3. Initialize a session
    user_id = "default_user"
    session_id = "default_session"
    
    # Try to load existing session; if not found, create a new one
    session = await session_service.get_session(
        app_name="chore_planning_agent",
        user_id=user_id,
        session_id=session_id
    )
    if not session:
        await session_service.create_session(
            user_id=user_id,
            session_id=session_id,
            app_name="chore_planning_agent",
        )
    
    # 4. Prompt the user for input and run the agent
    print("Agent is ready! Type your message below (type 'exit' or press Ctrl+C to quit):\n")
    
    pending_response = None
    while True:
        try:
            if not pending_response:
                query = input("User: ")
                if not query or not query.strip():
                    continue
                if query.lower() in ("exit", "quit"):
                    print("Goodbye!")
                    break
                
                # Capture and log user intent
                intent = logger.classify_intent(query)
                logger.info(
                    "user_query_received",
                    message=f"Received query: '{query}'",
                    extra={"query": query, "intent": intent}
                )
                new_message = types.Content(role='user', parts=[types.Part(text=query)])
            else:
                new_message = pending_response
                pending_response = None

            print("Agent: ", end="", flush=True)
            
            confirmation_needed = None
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
                
                # Check for tool confirmation request
                fcs = event.get_function_calls()
                if fcs:
                    for fc in fcs:
                        if fc.name == "adk_request_confirmation":
                            confirmation_needed = fc
                            orig_fc = fc.args.get("originalFunctionCall", {}) if fc.args else {}
                            logger.info(
                                "tool_confirmation_requested",
                                message="Agent is requesting tool confirmation.",
                                extra={
                                    "fc_id": fc.id,
                                    "tool_name": orig_fc.get("name"),
                                    "arguments": orig_fc.get("args")
                                }
                            )
                            
            print("\n")
            logger.info("agent_run_completed", message="Agent finished processing this turn.", extra={"status": "success"})
            
            if confirmation_needed:
                fc = confirmation_needed
                orig_fc = fc.args.get("originalFunctionCall", {}) if fc.args else {}
                orig_name = orig_fc.get("name", "Unknown Tool")
                orig_args = orig_fc.get("args", {})
                
                print(f"\n📢 [CONFIRMATION REQUIRED] The agent wants to execute '{orig_name}' with arguments:")
                for k, v in orig_args.items():
                    print(f"  • {k}: {v}")
                
                ans = input("Do you approve this action? (y/n): ")
                confirmed = ans.strip().lower() in ("y", "yes")
                
                logger.info(
                    "tool_confirmation_resolved",
                    message=f"User confirmation: {confirmed}",
                    extra={"confirmed": confirmed, "tool_name": orig_name}
                )
                
                # Build the FunctionResponse to send back to the agent
                response_payload = {
                    "confirmed": confirmed,
                    "payload": orig_args
                }
                
                function_response = types.FunctionResponse(
                    name="adk_request_confirmation",
                    id=fc.id,
                    response=response_payload
                )
                pending_response = types.Content(
                    role="user",
                    parts=[types.Part(function_response=function_response)]
                )
            
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

if __name__ == "__main__":
    asyncio.run(main())
