from google.adk.agents.llm_agent import Agent
from google.adk.tools import FunctionTool
from .tools import save_chore, get_chores, add_chore_to_calendar, verify_chore_policy

# Define calendar_agent with require_confirmation=True for its write tool
# We route this agent to gemini-1.5-flash for fast and cost-effective execution
calendar_tool = FunctionTool(func=add_chore_to_calendar, require_confirmation=True)

calendar_agent = Agent(
    model='gemini-3.5-flash',
    name='calendar_agent',
    description='A specialized agent for scheduling chore events on Google Calendar.',
    instruction="""
You are the Calendar Agent. You specialize in scheduling chore events on the user's Google Calendar.
When you are called, your only task is to call the `add_chore_to_calendar` tool with the provided chore parameters (Chore Name, Day of Week, Start Time, Duration, and Recurrence Rate).
Do not attempt to perform any other tasks. Once the tool executes, report the result to the user and transfer control back to the main agent `chore_planning_agent`.
""",
    tools=[calendar_tool],
)

# Define main planning agent which delegates scheduling to calendar_agent
# We route the coordinator to gemini-3.5-pro for deep reasoning and routing
root_agent = Agent(
    model='gemini-3.5-pro',
    name='chore_planning_agent',
    description='A helpful assistant for planning and saving chores.',
    instruction="""
You are an AI Assistant who helps users plan recurring chores. For each chore, please follow these steps: 

1. You must first collect the following information from the user: Chore Name, Day of Week, Start Time, Duration, Recurrence Rate. Please ensure that all parameters are collected before moving on.
2. Call the `verify_chore_policy` tool to ensure that the proposed chore conforms to safety policy guidelines (duration limit, quiet hours, etc.). If the policy check does not return "Passed", present the violation to the user and stop.
3. Call the `get_chores` tool to read from session memory and ensure that this chore does not overlap with previously saved chores.
4. Call the `save_chore` tool to save the new chore to session memory.
5. Transfer control to the `calendar_agent` by calling the `transfer_to_agent` tool, specifying `calendar_agent` as the target, to schedule the chore on the user's calendar.
""",
    tools=[save_chore, get_chores, verify_chore_policy],
    sub_agents=[calendar_agent]
)
