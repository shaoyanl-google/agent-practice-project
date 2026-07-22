import os
import json
import logging
from typing import Any, Optional
from google.adk.sessions import _session_util
from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session
from google.adk.events.event import Event
from google.adk.sessions.state import State
from typing_extensions import override

logger = logging.getLogger("google_adk." + __name__)

class FileSessionService(BaseSessionService):
    """A persistent NoSQL (document-store style) session service that stores session documents as JSON files."""

    def __init__(self, storage_dir: str = "sessions"):
        self.storage_dir = os.path.abspath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_filepath(self, app_name: str, user_id: str, session_id: str) -> str:
        app_dir = os.path.join(self.storage_dir, app_name, user_id)
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, f"{session_id}.json")

    def _get_user_state_path(self, app_name: str, user_id: str) -> str:
        app_dir = os.path.join(self.storage_dir, app_name, user_id)
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "user_state.json")

    def _get_app_state_path(self, app_name: str) -> str:
        app_dir = os.path.join(self.storage_dir, app_name)
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "app_state.json")

    @override
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        import time
        from google.adk.platform import uuid as platform_uuid
        
        sid = session_id or f"sess-{platform_uuid.uuid4()}"
        filepath = self._get_filepath(app_name, user_id, sid)
        
        if os.path.exists(filepath):
            from google.adk.errors.already_exists_error import AlreadyExistsError
            raise AlreadyExistsError(f"Session {sid} already exists.")
            
        session = Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=time.time()
        )
        
        # Merge existing user state into the new session state
        user_state = await self.get_user_state(app_name=app_name, user_id=user_id)
        for key, val in user_state.items():
            session.state[State.USER_PREFIX + key] = val
            
        # Merge existing app state into the new session state
        app_state = await self.get_app_state(app_name=app_name)
        for key, val in app_state.items():
            session.state[State.APP_PREFIX + key] = val
            
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(session.model_dump_json())
            
        return session

    @override
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        filepath = self._get_filepath(app_name, user_id, session_id)
        if not os.path.exists(filepath):
            return None
            
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        session = Session.model_validate(data)
        
        if config:
            if config.after_timestamp is not None:
                session.events = [e for e in session.events if e.timestamp >= config.after_timestamp]
            if config.num_recent_events is not None:
                session.events = session.events[-config.num_recent_events:]
                
        return session

    @override
    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        sessions = []
        app_path = os.path.join(self.storage_dir, app_name)
        if not os.path.exists(app_path):
            return ListSessionsResponse(sessions=[])
            
        users = [user_id] if user_id else os.listdir(app_path)
        
        for uid in users:
            user_path = os.path.join(app_path, uid)
            if not os.path.isdir(user_path):
                continue
            for file in os.listdir(user_path):
                if file.endswith(".json") and file != "user_state.json":
                    sid = file[:-5]
                    session = await self.get_session(app_name=app_name, user_id=uid, session_id=sid)
                    if session:
                        session.events = []
                        session.state = {}
                        sessions.append(session)
                        
        return ListSessionsResponse(sessions=sessions)

    @override
    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        filepath = self._get_filepath(app_name, user_id, session_id)
        if os.path.exists(filepath):
            os.remove(filepath)

    @override
    async def get_user_state(
        self, *, app_name: str, user_id: str
    ) -> dict[str, Any]:
        path = self._get_user_state_path(app_name, user_id)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def get_app_state(self, *, app_name: str) -> dict[str, Any]:
        path = self._get_app_state_path(app_name)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @override
    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event

        # Apply temp state to in-memory session first
        self._apply_temp_state(session, event)
        # Trim temp state before persisting
        event = self._trim_temp_delta_state(event)
        session.events.append(event)
        session.last_update_time = event.timestamp

        # Process user/app/session state updates
        if event.actions and event.actions.state_delta:
            state_deltas = _session_util.extract_state_delta(event.actions.state_delta)
            app_state_delta = state_deltas.get('app')
            user_state_delta = state_deltas.get('user')
            session_state_delta = state_deltas.get('session')

            if app_state_delta:
                app_state_path = self._get_app_state_path(session.app_name)
                app_state = await self.get_app_state(app_name=session.app_name)
                app_state.update(app_state_delta)
                with open(app_state_path, "w", encoding="utf-8") as f:
                    json.dump(app_state, f)
                # Apply updates to session
                for key, val in app_state_delta.items():
                    session.state[State.APP_PREFIX + key] = val

            if user_state_delta:
                user_state_path = self._get_user_state_path(session.app_name, session.user_id)
                user_state = await self.get_user_state(app_name=session.app_name, user_id=session.user_id)
                user_state.update(user_state_delta)
                with open(user_state_path, "w", encoding="utf-8") as f:
                    json.dump(user_state, f)
                # Apply updates to session
                for key, val in user_state_delta.items():
                    session.state[State.USER_PREFIX + key] = val

            if session_state_delta:
                session.state.update(session_state_delta)

        # Write final session state and events list back to JSON document
        filepath = self._get_filepath(session.app_name, session.user_id, session.id)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(session.model_dump_json())

        return event
