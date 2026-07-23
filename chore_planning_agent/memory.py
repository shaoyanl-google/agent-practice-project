import asyncio
import logging
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import LLMRegistry

logger = logging.getLogger("chore-planning-agent.memory")

async def consolidate_memory_background(session_service, app_name: str, user_id: str, session_id: str):
    """Consolidates memory/events in an explicit asyncio background task to guarantee UI unblocking."""
    # Run the consolidation in a separate task
    asyncio.create_task(_run_consolidation(session_service, app_name, user_id, session_id))

async def _run_consolidation(session_service, app_name: str, user_id: str, session_id: str):
    try:
        # Retrieve the session from SQLite database
        session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        if not session or len(session.events) < 8:
            # Only consolidate when we have sufficient history to avoid loss of active context
            return
        
        # Keep the last 3 events (typically the last user request and agent thoughts/responses)
        events_to_compact = session.events[:-3]
        events_to_keep = session.events[-3:]
        
        # Instantiate a lightweight model for background summarization
        llm = LLMRegistry.new_llm('gemini-3.5-flash')
        summarizer = LlmEventSummarizer(llm=llm)
        
        # Generate the consolidated summary event
        summary_event = await summarizer.maybe_compact_events(events_to_compact)
        if summary_event:
            # Update the session in storage with the compacted list
            session.events = [summary_event] + events_to_keep
            
            # Save the updated session state
            filepath = getattr(session_service, "_get_filepath", None)
            if filepath:
                # If using FileSessionService (test environments)
                path = filepath(app_name, user_id, session_id)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(session.model_dump_json())
            else:
                # If using SqliteSessionService
                async with session_service._get_db_connection() as db:
                    # Overwrite the events in the sqlite table for this session
                    await db.execute(
                        "DELETE FROM events WHERE app_name=? AND user_id=? AND session_id=?",
                        (app_name, user_id, session_id)
                    )
                    # Write back the compacted list
                    for ev in session.events:
                        ev_json = ev.model_dump_json()
                        await db.execute(
                            "INSERT OR REPLACE INTO events (id, app_name, user_id, session_id, invocation_id, timestamp, event_data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (ev.id, app_name, user_id, session_id, ev.invocation_id, ev.timestamp, ev_json)
                        )
                    await db.commit()
            
            logger.info("Background memory consolidation completed successfully.")
    except Exception as e:
        logger.error(f"Error during background memory consolidation: {e}")
