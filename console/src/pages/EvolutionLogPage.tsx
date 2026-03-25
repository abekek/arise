import { useEffect, useState } from "react";
import { fetchAgents, fetchEvolutions } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

interface EvolutionRow {
  timestamp: string;
  gaps_detected: string[];
  tools_synthesized: string[];
  tools_promoted: string[];
  tools_rejected: { name: string; reason: string }[];
  duration_ms: number;
  cost_usd: number;
  agent_name: string;
}

export default function EvolutionLogPage() {
  const [evolutions, setEvolutions] = useState<EvolutionRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const agents = await fetchAgents();
        const all: EvolutionRow[] = [];
        for (const agent of agents) {
          const evols = await fetchEvolutions(agent.id);
          if (Array.isArray(evols)) {
            for (const e of evols) {
              all.push({ ...e, agent_name: agent.name });
            }
          }
        }
        all.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        setEvolutions(all);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Loading evolution history...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-zinc-800">
        <h1 className="text-xl font-semibold text-zinc-100">Evolution Log</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {evolutions.length} evolution cycle{evolutions.length !== 1 ? "s" : ""} across all agents
        </p>
      </div>
      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-3">
        {evolutions.length === 0 ? (
          <p className="text-zinc-600 text-sm text-center py-8">No evolution cycles yet</p>
        ) : (
          evolutions.map((ev, i) => (
            <div
              key={i}
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-5"
            >
              <div className="flex items-center gap-3 mb-3">
                <Badge className="bg-amber-950 text-amber-400 border-0">Evolution</Badge>
                <span className="text-sm text-zinc-300 font-medium">{ev.agent_name}</span>
                <span className="text-xs font-mono text-zinc-500">
                  {new Date(ev.timestamp).toLocaleString()}
                </span>
                <span className="text-xs text-zinc-600">
                  {(ev.duration_ms / 1000).toFixed(1)}s
                </span>
              </div>

              {ev.gaps_detected.length > 0 && (
                <div className="mb-2">
                  <span className="text-xs text-zinc-500 mr-2">Gaps detected:</span>
                  {ev.gaps_detected.map((gap, j) => (
                    <span key={j} className="text-xs font-mono text-amber-400 mr-2">{gap}</span>
                  ))}
                </div>
              )}

              {ev.tools_promoted.length > 0 && (
                <div className="mb-2">
                  <span className="text-xs text-zinc-500 mr-2">Promoted:</span>
                  {ev.tools_promoted.map(name => (
                    <span key={name} className="text-xs font-mono text-emerald-400 bg-emerald-950 px-1.5 py-0.5 rounded mr-2">
                      {name}
                    </span>
                  ))}
                </div>
              )}

              {ev.tools_rejected.length > 0 && (
                <div>
                  <span className="text-xs text-zinc-500 mr-2">Rejected:</span>
                  {ev.tools_rejected.map((r, j) => (
                    <span key={j} className="text-xs font-mono text-red-400 mr-2">
                      {typeof r === "string" ? r : `${r.name} (${r.reason})`}
                    </span>
                  ))}
                </div>
              )}

              {ev.tools_synthesized.length > 0 && ev.tools_promoted.length === 0 && ev.tools_rejected.length === 0 && (
                <div>
                  <span className="text-xs text-zinc-500 mr-2">Synthesized:</span>
                  {ev.tools_synthesized.map(name => (
                    <span key={name} className="text-xs font-mono text-zinc-400 mr-2">{name}</span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
