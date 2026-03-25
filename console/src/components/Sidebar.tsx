import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { LayoutGrid, Wrench, Activity, Settings, Plus, Zap } from "lucide-react";
import { fetchAgents } from "@/lib/api";

interface Agent {
  id: string;
  name: string;
  status: "running" | "evolving" | "stopped" | string;
}

function statusDot(status: string) {
  if (status === "running") return "bg-emerald-400";
  if (status === "evolving") return "bg-amber-400";
  return "bg-zinc-500";
}

export default function Sidebar() {
  const location = useLocation();
  const [agents, setAgents] = useState<Agent[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchAgents();
        if (!cancelled) setAgents(Array.isArray(data) ? data : []);
      } catch {
        // backend may not be running
      }
    }

    load();
    const interval = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  function isActive(path: string) {
    return location.pathname === path || location.pathname.startsWith(path + "/");
  }

  function navClass(path: string) {
    const base =
      "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors";
    if (isActive(path)) return `${base} bg-zinc-800 text-zinc-100`;
    return `${base} text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60`;
  }

  return (
    <aside
      style={{ width: 220, minWidth: 220 }}
      className="flex flex-col h-screen border-r border-zinc-800 bg-zinc-950 shrink-0"
    >
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-zinc-800">
        <div className="flex items-center justify-center w-7 h-7 rounded-md bg-emerald-500/20 text-emerald-400">
          <Zap size={15} strokeWidth={2.5} />
        </div>
        <span className="font-semibold text-zinc-100 tracking-tight">ARISE</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3 flex flex-col gap-4">
        {/* Overview */}
        <section>
          <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
            Overview
          </p>
          <Link to="/" className={navClass("/")}>
            <LayoutGrid size={14} />
            Agents
          </Link>
        </section>

        {/* Agents */}
        {agents.length > 0 && (
          <section>
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
              Agents
            </p>
            <div className="flex flex-col gap-0.5">
              {agents.map(agent => (
                <Link
                  key={agent.id}
                  to={`/agents/${agent.id}`}
                  className={navClass(`/agents/${agent.id}`)}
                >
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${statusDot(agent.status)}`}
                  />
                  <span className="truncate">{agent.name}</span>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* New Agent */}
        <Link
          to="/?new=1"
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60 transition-colors"
        >
          <Plus size={14} />
          New Agent
        </Link>

        {/* Library */}
        <section>
          <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
            Library
          </p>
          <div className="flex flex-col gap-0.5">
            <Link to="/skills" className={navClass("/skills")}>
              <Wrench size={14} />
              All Skills
            </Link>
            <Link to="/evolutions" className={navClass("/evolutions")}>
              <Activity size={14} />
              Evolution Log
            </Link>
          </div>
        </section>
      </nav>

      {/* Settings */}
      <div className="px-2 py-3 border-t border-zinc-800">
        <Link to="/settings" className={navClass("/settings")}>
          <Settings size={14} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
