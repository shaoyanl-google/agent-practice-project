# ADK Skeleton Agent Project

This repository contains a skeleton project for a single AI agent built using the **Agent Development Kit (ADK)** Python framework.

## Project Structure

```
chore-planning-agent/
├── .venv/                 # Python virtual environment
├── chore_planning_agent/  # Agent definition folder
│   ├── .env               # API Keys and local configuration
│   ├── .gitignore         # Ignores local session cache
│   ├── __init__.py        # Package initializer
│   └── agent.py           # Main agent definition code
├── run_agent.py           # Script to run the agent programmatically
└── README.md              # This guide
```

## Getting Started

### 1. Prerequisites

Make sure you have Python 3.10 or later installed on your system.

### 2. Activate the Virtual Environment

Activate the pre-configured Python virtual environment:

```bash
# On macOS / Linux
source .venv/bin/activate

# On Windows (Command Prompt)
.venv\Scripts\activate.bat

# On Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Once activated, all `pip` and python commands will run using the project-local environment where `google-adk` is installed.

### 3. Configure Gemini API Key

ADK uses the Gemini API. You must configure your Google API key to run the agent.

1. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Open `chore_planning_agent/.env` in your editor.
3. Replace `YOUR_GEMINI_API_KEY` with your actual key:

```ini
GOOGLE_API_KEY=AIzaSy...
```

---

## Running the Agent

You can interact with your agent in three different ways:

### Option A: Interactive CLI

Use the ADK CLI to start a chat interface directly in your terminal:

```bash
adk run chore_planning_agent
```

### Option B: Programmatic Python Script

Run the helper Python script which executes the agent programmatically:

```bash
python run_agent.py
```

### Option C: Developer Web UI

ADK provides a web interface for testing and interacting with your agents. Run the following command from the project root:

```bash
adk web .
```

Then open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

*Note: In the top-left dropdown of the Web UI, select `chore_planning_agent` to start chatting.*

---

## Modifying the Agent

You can customize the agent's behavior by editing `chore_planning_agent/agent.py`.

For example, to give your agent a system instruction and a custom tool:

```python
from google.adk import Agent

# Define tools as standard Python functions with type hints and docstrings
def get_weather(location: str) -> str:
    """Returns the weather forecast for a location."""
    return f"The weather in {location} is sunny and 72°F."

root_agent = Agent(
    model='gemini-3.5-flash',
    name='chore-planning-agent',
    description='A helpful assistant with weather information.',
    instruction='Be helpful and polite. Use the weather tool when asked about the weather.',
    tools=[get_weather]
)
```
