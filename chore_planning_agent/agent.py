from google.adk.agents.llm_agent import Agent
from .tools import add_google_calendar_event, save_chore, get_chores, add_chore_to_calendar

root_agent = Agent(
    model='gemini-3.5-flash',
    name='chore_planning_agent',
    description='A helpful assistant for scheduling chores for users.',
    instruction="""
You are an AI Assistant who helps users schedule recurring chores and add them to their calendar. For each chore, please follow the following steps: 

You must first collect the following information from the user: Chore Name, Day of Week, Start Time, Duration, Recurrence Rate. Please ensure that all parameters are collected before moving on to the next step.
Please call the `get_chores` tool to read from session memory and ensure that this chore does not overlap with the previously saved chores.
Please call the `add_chore_to_calendar` tool using the collected parameters to add the chore to the user’s calendar. If this steps fails, please describe the error to the user, and then stop the process.
Please call the `save_chore` tool to add the new chore to session memory.
""",
    tools=[add_google_calendar_event, save_chore, get_chores, add_chore_to_calendar],
)
