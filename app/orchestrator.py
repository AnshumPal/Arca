import logging

from app.agents import get_agent
from app.config import settings
from app.router import classify as classify_keyword

logger = logging.getLogger(__name__)

# Canned truthful answer for meta-questions about Arca itself.
# Bypasses the LLM entirely so small models can't confabulate about the
# real-world musician Arca or the crypto company Arca Labs.
ARCA_INFO_RESPONSE = """Arca is a self-improving multi-agent AI platform built by \
Anshum Pal as a portfolio project — not a company, product, musician, or crypto \
service.

Three specialised agents handle live requests: intake (general questions), research \
(analysis and explanation), and action (task execution and structured output). \
Every interaction is scored automatically across four dimensions — latency, output \
length, user feedback, and error rate. Experimental agent variants run in sandboxed \
shadow mode against live traffic to be tested safely, and a nightly optimizer \
detects failure patterns and proposes improved prompts. Nothing reaches production \
without passing a 4-check gate and explicit human approval.

Stack: FastAPI · PostgreSQL · Next.js · Docker · OpenAI SDK · APScheduler · deployed \
on Render + Vercel + Neon at zero monthly cost.

Live demo: https://arca-1.vercel.app · Code: https://github.com/AnshumPal/Arca"""

ARCA_INFO_PROMPT = "[intercepted by router: canned response, no LLM call]"


async def _classify(message: str) -> str:
    """
    Pick a classifier based on the USE_SEMANTIC_ROUTER feature flag.
    Default (false) → fast keyword classifier — no LLM cost, no test breakage.
    Enabled (true)  → LLM-based semantic classifier — ~500ms latency, 95%+ accuracy.
    """
    if settings.use_semantic_router:
        # Lazy import to avoid loading the LLM client when the flag is off
        from app.semantic_router import classify_semantic
        return await classify_semantic(message)
    return classify_keyword(message)


async def handle(message: str, session_id: str | None) -> dict:
    """
    Classify the message, pick the right agent, run it.
    Returns a dict with agent_id, response, and prompt_used.

    Meta-questions about Arca itself are short-circuited with a canned response
    to prevent small-model confabulation. These traces are logged under
    agent_id='agent-1' (intake) so they don't pollute eval scores of the other
    agents, but marked in prompt_used for auditability.
    """
    agent_id = await _classify(message)
    logger.info("Orchestrator routing session=%s to %s", session_id, agent_id)

    # Router short-circuit: return canned answer without any LLM call
    if agent_id == "arca-info":
        return {
            "agent_id": "agent-1",  # log under intake so scoring stays consistent
            "response": ARCA_INFO_RESPONSE,
            "prompt_used": ARCA_INFO_PROMPT,
        }

    agent = get_agent(agent_id)
    response, prompt_used = await agent["run"](message)
    return {
        "agent_id": agent_id,
        "response": response,
        "prompt_used": prompt_used,
    }
