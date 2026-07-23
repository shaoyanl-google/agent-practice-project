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

# Patch LLMRegistry to map gemini-3.5-pro to gemini-3.5-flash due to sandbox API limitations
_orig_new_llm = LLMRegistry.new_llm
def _patched_new_llm(model_name: str, *args, **kwargs):
    if model_name == "gemini-3.5-pro":
        model_name = "gemini-3.5-flash"
    return _orig_new_llm(model_name, *args, **kwargs)
LLMRegistry.new_llm = _patched_new_llm
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from chore_planning_agent.logger import StructuredLogger
from chore_planning_agent.memory import consolidate_memory_background
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Setup OpenTelemetry distributed tracing provider
provider = TracerProvider()
processor = SimpleSpanProcessor(ConsoleSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("chore-planning-agent.runner")
logger = StructuredLogger(service_name="chore-planning-agent.runner")

# Load environment variables from the agent's .env file (for local fallbacks)
agent_dir = os.path.join(os.path.dirname(__file__), "chore_planning_agent")
load_dotenv(os.path.join(agent_dir, ".env"))

# Import API Key injection helper
from chore_planning_agent.secrets import load_google_api_key
load_google_api_key("gemini-api-key")

# Import the root agent defined in the skeleton project
from chore_planning_agent.agent import root_agent

async def main():
    # 1. Check if the API key is set
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        print("WARNING: GOOGLE_API_KEY is not set or is using the placeholder value.")
        print("Please configure a valid Gemini API key via Google Cloud Secret Manager ('gemini-api-key') or in 'chore_planning_agent/.env'.")
        print("You can get a free key from: https://aistudio.google.com/apikey\n")
        return

    # 2. Instantiate SqliteSessionService (robust persistent relational database)
    session_service = SqliteSessionService(db_path="sessions.db")
    
    # Build ADK App container
    app = App(
        name="chore_planning_agent",
        root_agent=root_agent
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
                
                # Redact PII from the user query before passing it to agent or logs
                redacted_query = logger.redact_pii(query)
                
                # Capture and log user intent
                intent = logger.classify_intent(redacted_query)
                logger.info(
                    "user_query_received",
                    message=f"Received query: '{redacted_query}'",
                    extra={"query": redacted_query, "intent": intent}
                )
                new_message = types.Content(role='user', parts=[types.Part(text=redacted_query)])
            else:
                new_message = pending_response
                pending_response = None

            print("Agent: ", end="", flush=True)
            
            confirmation_needed = None
            # 5. Stream responses from the agent wrapped in OpenTelemetry trace span
            with tracer.start_as_current_span("agent_turn_execution") as span:
                span.set_attribute("session_id", session_id)
                if not pending_response:
                    span.set_attribute("user_query", logger.redact_pii(query))
                    span.set_attribute("classified_intent", intent)
                
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
                                span.set_attribute("tool_confirmation_requested", fc.id)
            
            print("\n")
            logger.info("agent_run_completed", message="Agent finished processing this turn.", extra={"status": "success"})
            
            # Asynchronously trigger memory consolidation in a background task (guarantees UI unblocking)
            await consolidate_memory_background(session_service, "chore_planning_agent", user_id, session_id)
            
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
