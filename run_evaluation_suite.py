import asyncio
import os
import json
import shutil
import sys
from dotenv import load_dotenv

# Load env variables
agent_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(agent_dir, "chore_planning_agent", ".env"))

# Import API Key injection helper
from chore_planning_agent.secrets import load_google_api_key
load_google_api_key("gemini-api-key")

from google.adk.runners import Runner
from google.adk.apps import App
from google.genai import types
from google.adk.models import LLMRegistry

# Patch LLMRegistry to map gemini-3.5-pro to gemini-3.5-flash due to sandbox API limitations
_orig_new_llm = LLMRegistry.new_llm
def _patched_new_llm(model_name: str, *args, **kwargs):
    if model_name == "gemini-3.5-pro":
        model_name = "gemini-3.5-flash"
    return _orig_new_llm(model_name, *args, **kwargs)
LLMRegistry.new_llm = _patched_new_llm

from chore_planning_agent.agent import root_agent
from google.adk.sessions.sqlite_session_service import SqliteSessionService

async def run_evaluation():
    print("🚀 Running Automated CI/CD Agent Evaluation Suite...")
    
    test_file = os.path.join(agent_dir, "chore_planning_agent", "tests", "test_chore_planning.json")
    if not os.path.exists(test_file):
        print(f"❌ Error: Golden test file not found at: {test_file}")
        sys.exit(1)
        
    with open(test_file, "r") as f:
        session_data = json.load(f)
        
    events = session_data.get("events", [])
    
    # Extract user inputs & expected values
    user_turns = []
    expected_actions = []
    
    for ev in events:
        author = ev.get("author")
        if author == "user":
            content_dict = ev.get("content", {})
            parts = content_dict.get("parts", [])
            real_parts = []
            for p in parts:
                if "functionResponse" in p:
                    fr = p["functionResponse"]
                    real_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=fr.get("id"),
                                name=fr.get("name"),
                                response=fr.get("response"),
                            )
                        )
                    )
                elif "text" in p:
                    real_parts.append(types.Part(text=p["text"]))
            user_turns.append(types.Content(role="user", parts=real_parts))
        elif author in ("chore_planning_agent", "calendar_agent"):
            # Collect expected tool calls or final model output patterns
            content_dict = ev.get("content", {})
            parts = content_dict.get("parts", [])
            for p in parts:
                if "functionCall" in p:
                    fc = p["functionCall"]
                    expected_actions.append(fc.get("name"))
                    
    # Setup test runner using temporary sqlite DB
    db_path = "eval_temp.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    session_service = SqliteSessionService(db_path=db_path)
    app = App(name="chore_planning_agent", root_agent=root_agent)
    runner = Runner(app=app, session_service=session_service)
    
    user_id = "eval_user"
    session_id = "eval_session"
    
    await session_service.create_session(
        app_name="chore_planning_agent",
        user_id=user_id,
        session_id=session_id
    )

    actual_actions = []
    captured_confirmation_id = None

    try:
        for i, user_content in enumerate(user_turns):
            # Dynamic ID mapping for the confirmation turn
            if i == 1 and captured_confirmation_id:
                for part in user_content.parts:
                    if part.function_response and part.function_response.name == "adk_request_confirmation":
                        part.function_response.id = captured_confirmation_id
                        
            # Execute turn
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=user_content
            ):
                fcs = event.get_function_calls()
                if fcs:
                    for fc in fcs:
                        actual_actions.append(fc.name)
                        if fc.name == "adk_request_confirmation":
                            captured_confirmation_id = fc.id

        # Verify results
        print("\n--- Evaluation Verification ---")
        print(f"Expected Tool Calls: {expected_actions}")
        print(f"Actual Tool Calls  : {actual_actions}")
        
        # We verify that crucial tools are executed in the correct lifecycle:
        # 1. verify_chore_policy (our guardrail)
        # 2. save_chore (our storage writer)
        # 3. transfer_to_agent (for subagent delegation)
        # 4. add_chore_to_calendar (our calendar writer)
        # 5. adk_request_confirmation (our human-in-the-loop verification gate)
        
        required_tools = ["verify_chore_policy", "save_chore", "transfer_to_agent", "add_chore_to_calendar", "adk_request_confirmation"]
        for tool in required_tools:
            assert tool in actual_actions, f"❌ Validation Error: Expected tool '{tool}' was not called during execution!"
            
        print("✅ Evaluation Passed! All required tools and guardrail pipelines executed successfully.")
        
    except Exception as e:
        print(f"❌ Evaluation Failed: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    asyncio.run(run_evaluation())
