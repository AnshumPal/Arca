# Backward-compatibility shim — kept so any code that imports
# from app.agent still works. All real logic lives in app/agents/.
from app.agents.intake import AGENT_ID, DESCRIPTION, run  # noqa: F401
