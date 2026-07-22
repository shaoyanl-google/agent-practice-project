import os
import httpx
import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ValidationError
from google.auth import default
from google.auth.transport.requests import Request
from google.auth.exceptions import DefaultCredentialsError
from .logger import StructuredLogger

logger = StructuredLogger(service_name="chore-planning-agent.tools")

class GoogleCalendarEventInput(BaseModel):
    summary: str = Field(..., min_length=1)
    start_time: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?$')
    end_time: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?$')
    description: Optional[str] = ""
    location: Optional[str] = ""
    recurrence: Optional[List[str]] = None

class SaveChoreInput(BaseModel):
    chore_name: str = Field(..., min_length=1)
    status: Optional[str] = "pending"
    due_time: Optional[str] = None

class AddChoreToCalendarInput(BaseModel):
    chore_name: str = Field(..., min_length=1)
    day_of_week: str = Field(..., pattern=r'^(?i)(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$')
    recurrence_rate: str = Field(..., min_length=1)
    time: str = Field(..., pattern=r'^\d{2}:\d{2}$')
    duration: str = Field(..., min_length=1)

def add_google_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    recurrence: list[str] = None,
) -> str:
    """Adds an event to the user's primary Google Calendar.

    Args:
        summary: The title or summary of the event (e.g., "Mow the lawn").
        start_time: The start time of the event in ISO 8601 format (e.g., "2026-07-21T15:00:00").
        end_time: The end time of the event in ISO 8601 format (e.g., "2026-07-21T16:00:00").
        description: An optional description of the event.
        location: An optional location for the event.
        recurrence: Optional list of recurrence RRULE strings.

    Returns:
        A message indicating success with the event link, or a descriptive error message.
    """
    logger.info("validation_started", extra={"tool": "add_google_calendar_event", "summary": summary})
    try:
        # Validate arguments using explicit JSON schema
        GoogleCalendarEventInput(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            recurrence=recurrence
        )
        logger.info("validation_passed", extra={"tool": "add_google_calendar_event"})
    except ValidationError as e:
        logger.error("validation_failed", extra={"tool": "add_google_calendar_event", "errors": e.errors()})
        return f"Validation Error: Invalid arguments passed to 'add_google_calendar_event'. Details: {e.errors()}"

    # 1. Attempt to get access token from environment override
    access_token = os.environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN")
    quota_project = os.environ.get("GOOGLE_CALENDAR_QUOTA_PROJECT")
    
    if not access_token:
        # 2. Fallback to Application Default Credentials (ADC)
        try:
            scopes = ["https://www.googleapis.com/auth/calendar.events"]
            creds, project = default(scopes=scopes)
            if not creds.valid:
                creds.refresh(Request())
            access_token = creds.token
            if hasattr(creds, "quota_project_id") and creds.quota_project_id:
                quota_project = creds.quota_project_id
        except DefaultCredentialsError:
            return (
                "Authentication Error: Google credentials could not be found.\n"
                "To resolve this, please do one of the following:\n"
                "1. Run 'gcloud auth application-default login' in your terminal.\n"
                "2. Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to a service account key JSON file.\n"
                "3. Set the GOOGLE_CALENDAR_ACCESS_TOKEN environment variable in your .env file with a valid OAuth2 access token."
            )
        except Exception as e:
            return f"Authentication Error: Failed to load Google credentials: {e}"

    # 3. Call the Google Calendar API to insert the event
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if quota_project:
        headers["x-goog-user-project"] = quota_project
    
    event_body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {
            "dateTime": start_time,
            # We default to local system/user time zone if no offset is provided, or UTC
            "timeZone": "UTC" if "Z" in start_time or "+" in start_time else None
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "UTC" if "Z" in end_time or "+" in end_time else None
        },
    }
    if recurrence:
        event_body["recurrence"] = recurrence
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=event_body, timeout=10.0)
            
        if response.status_code == 200:
            event_data = response.json()
            return f"Event '{summary}' successfully created! Link: {event_data.get('htmlLink')}"
        elif response.status_code == 401:
            return "API Error: Unauthorized. The access token might be invalid or expired."
        else:
            return f"API Error: Failed to create event (Status code: {response.status_code}). Response: {response.text}"
            
    except httpx.RequestError as e:
        return f"Network Error: Failed to connect to Google Calendar API: {e}"
    except Exception as e:
        return f"Unexpected Error: {e}"

from google.adk.tools.tool_context import ToolContext

def save_chore(
    chore_name: str,
    status: str = "pending",
    due_time: str = None,
    tool_context: ToolContext = None,
) -> str:
    """Saves a chore to the user's structured list of chores in session memory.

    Args:
        chore_name: The name of the chore (e.g., "Take out the trash").
        status: The current status of the chore (e.g., "pending", "completed").
        due_time: Optional due time in ISO format or descriptive string.
        tool_context: The tool context injected by the ADK framework.

    Returns:
        A confirmation message.
    """
    logger.info("validation_started", extra={"tool": "save_chore", "chore_name": chore_name})
    try:
        # Validate arguments using explicit JSON schema
        SaveChoreInput(
            chore_name=chore_name,
            status=status,
            due_time=due_time
        )
        logger.info("validation_passed", extra={"tool": "save_chore"})
    except ValidationError as e:
        logger.error("validation_failed", extra={"tool": "save_chore", "errors": e.errors()})
        return f"Validation Error: Invalid arguments passed to 'save_chore'. Details: {e.errors()}"

    if tool_context is None:
        return "Error: ToolContext was not provided."
        
    state = tool_context.state
    if "chores" not in state:
        state["chores"] = []
        
    chores = list(state["chores"])
    # Check if chore already exists, update it if so
    for chore in chores:
        if chore["chore_name"].lower() == chore_name.lower():
            chore["status"] = status
            if due_time:
                chore["due_time"] = due_time
            state["chores"] = chores
            return f"Updated chore '{chore_name}' status to '{status}'."
            
    # Add new chore
    chores.append({
        "chore_name": chore_name,
        "status": status,
        "due_time": due_time
    })
    state["chores"] = chores
    return f"Saved chore '{chore_name}' with status '{status}'."

def get_chores(tool_context: ToolContext = None) -> str:
    """Retrieves the list of saved chores from session memory.

    Args:
        tool_context: The tool context injected by the ADK framework.

    Returns:
        A formatted list of chores or a message if no chores are found.
    """
    if tool_context is None:
        return "Error: ToolContext was not provided."
        
    state = tool_context.state
    chores = state.get("chores", [])
    if not chores:
        return "You have no saved chores in session memory."
        
    res = ["Here are your saved chores:"]
    for i, chore in enumerate(chores, 1):
        due = f" (due: {chore['due_time']})" if chore.get('due_time') else ""
        res.append(f"{i}. [{chore['status']}] {chore['chore_name']}{due}")
    return "\n".join(res)

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def calculate_event_times(
    day_of_week: str,
    time_str: str,
    duration_str: str
) -> tuple[str, str]:
    # 1. Parse time (e.g. "14:00" or "14:00:00")
    # Supports "HH:MM"
    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    
    # 2. Get today's date in local/UTC
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    
    target_weekday = DAYS.index(day_of_week.lower().strip())
    days_ahead = target_weekday - today.weekday()
    
    if days_ahead < 0:
        days_ahead += 7
    elif days_ahead == 0:
        # It is today. Check if the time is in the past
        event_time_today = datetime.datetime.combine(today, datetime.time(hour, minute), tzinfo=datetime.timezone.utc)
        if event_time_today < now:
            days_ahead += 7
            
    target_date = today + datetime.timedelta(days_ahead)
    start_dt = datetime.datetime.combine(target_date, datetime.time(hour, minute), tzinfo=datetime.timezone.utc)
    
    # 3. Parse duration (e.g. "1 hour", "30 minutes", "2 hours")
    duration_str = duration_str.lower().strip()
    duration_delta = datetime.timedelta(hours=1) # Default
    
    if "hour" in duration_str:
        num = int(duration_str.split("hour")[0].strip())
        duration_delta = datetime.timedelta(hours=num)
    elif "minute" in duration_str:
        num = int(duration_str.split("minute")[0].strip())
        duration_delta = datetime.timedelta(minutes=num)
        
    end_dt = start_dt + duration_delta
    
    return start_dt.isoformat(), end_dt.isoformat()

def add_chore_to_calendar(
    chore_name: str,
    day_of_week: str,
    recurrence_rate: str,
    time: str,
    duration: str,
) -> str:
    """Saves a recurring chore and schedules it on the user's Google Calendar.

    Args:
        chore_name: The name of the chore (e.g., "Mow the lawn").
        day_of_week: The day of the week to run the chore (e.g., "Monday", "Tuesday").
        recurrence_rate: How often it recurs (e.g., "weekly", "daily").
        time: The time of day to start in 24-hour format (e.g., "14:00").
        duration: The duration of the chore (e.g., "1 hour", "30 minutes").

    Returns:
        The result of scheduling the chore.
    """
    logger.info("validation_started", extra={"tool": "add_chore_to_calendar", "chore_name": chore_name})
    try:
        # Validate arguments using explicit JSON schema
        AddChoreToCalendarInput(
            chore_name=chore_name,
            day_of_week=day_of_week,
            recurrence_rate=recurrence_rate,
            time=time,
            duration=duration
        )
        logger.info("validation_passed", extra={"tool": "add_chore_to_calendar"})
    except ValidationError as e:
        logger.error("validation_failed", extra={"tool": "add_chore_to_calendar", "errors": e.errors()})
        return f"Validation Error: Invalid arguments passed to 'add_chore_to_calendar'. Details: {e.errors()}"

    try:
        # Calculate start and end times
        start_time, end_time = calculate_event_times(day_of_week, time, duration)
        
        # Build RRULE recurrence string
        freq = "WEEKLY"
        rec_lower = recurrence_rate.lower().strip()
        if "day" in rec_lower:
            freq = "DAILY"
        elif "week" in rec_lower:
            freq = "WEEKLY"
        elif "month" in rec_lower:
            freq = "MONTHLY"
            
        # Map day of week to 2-letter code for BYDAY
        day_map = {
            "monday": "MO", "tuesday": "TU", "wednesday": "WE",
            "thursday": "TH", "friday": "FR", "saturday": "SA", "sunday": "SU"
        }
        day_code = day_map.get(day_of_week.lower().strip(), "MO")
        
        recurrence_rule = f"RRULE:FREQ={freq}"
        if freq == "WEEKLY":
            recurrence_rule += f";BYDAY={day_code}"
            
        recurrence = [recurrence_rule]
        
        description = f"Recurring chore: {recurrence_rate} on {day_of_week} at {time}."
        
        # Call add_google_calendar_event
        return add_google_calendar_event(
            summary=chore_name,
            start_time=start_time,
            end_time=end_time,
            description=description,
            recurrence=recurrence
        )
    except Exception as e:
        return f"Error while preparing calendar event: {e}"
