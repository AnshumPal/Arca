from app.agents.action import AGENT_ID as ACTION_ID
from app.agents.action import DESCRIPTION as ACTION_DESC
from app.agents.action import run as action_run
from app.agents.intake import AGENT_ID as INTAKE_ID
from app.agents.intake import DESCRIPTION as INTAKE_DESC
from app.agents.intake import run as intake_run
from app.agents.research import AGENT_ID as RESEARCH_ID
from app.agents.research import DESCRIPTION as RESEARCH_DESC
from app.agents.research import run as research_run

REGISTRY: dict[str, dict] = {
    INTAKE_ID:   {"run": intake_run,   "description": INTAKE_DESC},
    RESEARCH_ID: {"run": research_run, "description": RESEARCH_DESC},
    ACTION_ID:   {"run": action_run,   "description": ACTION_DESC},
}


def get_agent(agent_id: str) -> dict:
    if agent_id not in REGISTRY:
        raise ValueError(f"Unknown agent: {agent_id}")
    return REGISTRY[agent_id]
