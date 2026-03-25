import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchAgents } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Plus, Bot, TrendingUp, BookOpen } from "lucide-react";
import CreateAgentDialog from "@/components/CreateAgentDialog";

interface Episode {
  id: string;
  task: string;
  status: "ok" | "fail" | "evolving" | string;
  reward?: number;
}

interface Agent {
  id: string;
  name: string;
  model: string;
  status: "running" | "evolving" | "stopped" | string;
  skills_count?: number;
  success_rate?: number;
  episodes_count?: number;
  progress?: number;
  recent_episodes?: Episode[];
}

function statusBadge(status: string) {
  if (status === "running")
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-950 border border-emerald-900/60 px-2 py-0.5 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        running
      </span>
    );
  if (status === "evolving")
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-400 bg-amber-950 border border-amber-900/60 px-2 py-0.5 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        evolving
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 bg-zinc-800 border border-zinc-700 px-2 py-0.5 rounded-full">
      <span className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
      stopped
    </span>
  );
}

function episodeColor(status: string) {
  if (status === "ok") return "text-emerald-400";
  if (status === "fail") return "text-red-400";
  if (status === "evolving") return "text-amber-400";
  return "text-zinc-400";
}

function episodeIcon(status: string) {
  if (status === "ok") return "✓";
  if (status === "fail") return "✗";
  if (status === "evolving") return "⟳";
  return "·";
}

function AgentCard({ agent, onClick }: { agent: Agent; onClick: () => void }) {
  const skills = agent.skills_count ?? 0;
  const successRate = agent.success_rate ?? 0;
  const episodes = agent.episodes_count ?? 0;
  const progress = agent.progress ?? 0;
  const recentEpisodes = agent.recent_episodes ?? [];

  return (
    <div
      onClick={onClick}
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 cursor-pointer hover:border-zinc-600 hover:bg-zinc-800/70 transition-all group flex flex-col gap-3"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1 min-w-0">
          <h3 className="font-semibold text-zinc-100 truncate group-hover:text-white">
            {agent.name}
          </h3>
          <p className="text-xs text-zinc-500 font-mono truncate">{agent.model}</p>
        </div>
        {statusBadge(agent.status)}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-zinc-800/60 rounded-md p-2.5 text-center">
          <p className="text-base font-semibold text-zinc-100">{skills}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5 flex items-center justify-center gap-1">
            <BookOpen size={9} /> Skills
          </p>
        </div>
        <div className="bg-zinc-800/60 rounded-md p-2.5 text-center">
          <p className="text-base font-semibold text-zinc-100">
            {successRate > 0 ? `${Math.round(successRate * 100)}%` : "—"}
          </p>
          <p className="text-[10px] text-zinc-500 mt-0.5 flex items-center justify-center gap-1">
            <TrendingUp size={9} /> Success
          </p>
        </div>
        <div className="bg-zinc-800/60 rounded-md p-2.5 text-center">
          <p className="text-base font-semibold text-zinc-100">{episodes}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5 flex items-center justify-center gap-1">
            <Bot size={9} /> Episodes
          </p>
        </div>
      </div>

      {/* Progress bar */}
      {progress > 0 && (
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] text-zinc-600">Training progress</span>
            <span className="text-[10px] text-zinc-500">{Math.round(progress * 100)}%</span>
          </div>
          <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Recent episodes */}
      {recentEpisodes.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-zinc-800 pt-2.5">
          <p className="text-[10px] text-zinc-600 mb-0.5">Recent episodes</p>
          {recentEpisodes.slice(0, 3).map((ep, i) => (
            <div key={ep.id ?? i} className="flex items-center gap-2">
              <span className={`text-xs font-mono ${episodeColor(ep.status)}`}>
                {episodeIcon(ep.status)}
              </span>
              <span className="text-xs text-zinc-400 truncate flex-1">{ep.task}</span>
              {ep.reward !== undefined && (
                <span className="text-[10px] text-zinc-600 font-mono shrink-0">
                  r={ep.reward.toFixed(2)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AgentsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(searchParams.get("new") === "1");

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchAgents();
        setAgents(Array.isArray(data) ? data : []);
      } catch {
        setAgents([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function openDialog() {
    setDialogOpen(true);
  }

  function closeDialog() {
    setDialogOpen(false);
    setSearchParams({});
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800 shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Agents</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            {agents.length} agent{agents.length !== 1 ? "s" : ""} in your fleet
          </p>
        </div>
        <Button
          onClick={openDialog}
          className="bg-emerald-600 hover:bg-emerald-500 text-white gap-1.5"
          size="sm"
        >
          <Plus size={14} /> New Agent
        </Button>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center h-48 text-zinc-600 text-sm">
            Loading agents...
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {agents.map(agent => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onClick={() => navigate(`/agents/${agent.id}`)}
              />
            ))}

            {/* Create new card */}
            <div
              onClick={openDialog}
              className="border-2 border-dashed border-zinc-800 rounded-lg p-6 cursor-pointer hover:border-zinc-600 hover:bg-zinc-900/40 transition-all flex flex-col items-center justify-center gap-2 min-h-[180px] group"
            >
              <div className="w-9 h-9 rounded-full border-2 border-dashed border-zinc-700 group-hover:border-zinc-500 flex items-center justify-center transition-colors">
                <Plus size={16} className="text-zinc-600 group-hover:text-zinc-400" />
              </div>
              <p className="text-sm text-zinc-600 group-hover:text-zinc-400 transition-colors font-medium">
                Create new agent
              </p>
            </div>
          </div>
        )}
      </div>

      <CreateAgentDialog open={dialogOpen} onClose={closeDialog} />
    </div>
  );
}
