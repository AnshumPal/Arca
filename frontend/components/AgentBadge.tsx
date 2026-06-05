const labels: Record<string, string> = {
  "agent-1": "Intake",
  "agent-2": "Research",
  "agent-3": "Action",
};

export function AgentBadge({ agentId }: { agentId: string }) {
  const label = labels[agentId] || agentId;
  return (
    <span className="badge border border-[#c87f4a]/40 bg-[#c87f4a]/10 text-[#c87f4a]">
      {label}
    </span>
  );
}
