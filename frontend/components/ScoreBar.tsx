interface ScoreBarProps {
  label: string;
  value: number; // 0.0 - 1.0
}

export function ScoreBar({ label, value }: ScoreBarProps) {
  const pct = Math.round(value * 100);
  // Single accent color — opacity varies with score
  const opacity =
    value >= 0.8 ? "opacity-100"
      : value >= 0.6 ? "opacity-80"
      : value >= 0.4 ? "opacity-60"
      : "opacity-40";

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-[#8a8378] capitalize tracking-wide">{label}</span>
        <span className="font-mono text-[#f5f1ea]">{value.toFixed(2)}</span>
      </div>
      <div className="h-[3px] w-full overflow-hidden rounded-full bg-[#1a1a1a]">
        <div
          className={`h-full transition-all duration-700 bg-[#c87f4a] ${opacity}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
