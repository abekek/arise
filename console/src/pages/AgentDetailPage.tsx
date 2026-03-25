import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchAgent,
  fetchSkills,
  fetchTrajectories,
  fetchEvolutions,
  runTask,
  createLiveSocket,
} from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ChevronLeft, Play, Square, Settings2 } from "lucide-react";

interface Agent {
  id: string;
  name: string;
  model: string;
  status: string;
  skills_count?: number;
  success_rate?: number;
  episodes?: number;
  system_prompt?: string;
  reward_function?: string;
  sandbox_backend?: string;
  failure_threshold?: number;
  allowed_imports?: string[];
  library_version?: number;
}

interface Skill {
  id: string;
  name: string;
  status: string;
  success_rate?: number;
  invocations?: number;
  origin?: string;
}

interface Trajectory {
  task: string;
  status: string;
  reward: number;
  steps_count: number;
  skills_count: number;
  outcome: string;
  timestamp: string;
}

interface Evolution {
  timestamp: string;
  gaps_detected: string[];
  tools_synthesized: string[];
  tools_promoted: string[];
  tools_rejected: { name: string; reason: string }[];
  duration_ms: number;
  cost_usd: number;
}

interface LiveEvent {
  type: string;
  message: string;
  ts?: string;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "running")
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-400 bg-emerald-950 border border-emerald-900/60 px-2.5 py-1 rounded-full">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        running
      </span>
    );
  if (status === "evolving")
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-400 bg-amber-950 border border-amber-900/60 px-2.5 py-1 rounded-full">
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
        evolving
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-400 bg-zinc-800 border border-zinc-700 px-2.5 py-1 rounded-full">
      <span className="w-2 h-2 rounded-full bg-zinc-500" />
      stopped
    </span>
  );
}

function eventColor(type: string) {
  if (type === "ok" || type === "success") return "text-emerald-400";
  if (type === "fail" || type === "error") return "text-red-400";
  if (type === "evolving" || type === "evolution" || type === "evolve") return "text-amber-400";
  if (type === "info") return "text-zinc-400";
  return "text-zinc-500";
}

function eventPrefix(type: string) {
  if (type === "ok" || type === "success") return "✓";
  if (type === "fail" || type === "error") return "✗";
  if (type === "evolving" || type === "evolution" || type === "evolve") return "⚡";
  return "›";
}

function skillStatusBadge(status: string) {
  const cls =
    status === "active"
      ? "text-emerald-400 bg-emerald-950 border-emerald-900/60"
      : "text-zinc-400 bg-zinc-800 border-zinc-700";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${cls}`}>
      {status}
    </span>
  );
}

function trajectoryStatusBadge(status: string) {
  const map: Record<string, string> = {
    ok: "text-emerald-400 bg-emerald-950 border-emerald-900/60",
    success: "text-emerald-400 bg-emerald-950 border-emerald-900/60",
    fail: "text-red-400 bg-red-950 border-red-900/60",
    failed: "text-red-400 bg-red-950 border-red-900/60",
  };
  const cls = map[status] ?? "text-zinc-400 bg-zinc-800 border-zinc-700";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${cls}`}>
      {status}
    </span>
  );
}


// --- Live Tab ---
function formatWsEvent(data: any): { type: string; message: string }[] | null {
  let type = "info";
  let message = "";

  switch (data.type) {
    case "episode_start":
      message = `▶ Episode ${data.episode}: ${data.task}`;
      break;
    case "episode_end":
      type = data.status === "ok" ? "success" : "error";
      message = `Episode ${data.episode} | ${data.status?.toUpperCase()} | reward=${Number(data.reward || 0).toFixed(2)} | skills=${data.skills}`;
      if (data.result_preview) {
        return [
          { type, message },
          { type: "info", message: `→ ${data.result_preview}` },
        ];
      }
      break;
    case "evolution_start":
      type = "evolve";
      message = `⚡ Evolution triggered — ${data.reason || "analyzing gaps..."}`;
      break;
    case "forge_detecting":
      type = "evolve";
      message = `  Analyzing ${data.failure_count} failure trajectories...`;
      break;
    case "gap_detected":
      type = "evolve";
      message = `  Gap detected: ${data.description || data.suggested_name}`;
      break;
    case "synthesis_start":
      type = "evolve";
      message = `  Synthesizing '${data.name}'...`;
      break;
    case "test_result":
      type = data.failed === 0 ? "success" : "error";
      message = `  Tests: ${data.passed} passed, ${data.failed} failed`;
      break;
    case "skill_promoted":
      type = "success";
      message = `  ✓ Skill '${data.name}' promoted!`;
      break;
    case "skill_rejected":
      type = "error";
      message = `  ✗ Skill '${data.name}' rejected: ${data.reason}`;
      break;
    case "evolution_end":
      type = "evolve";
      message = `⚡ Evolution complete — ${data.promoted?.length || 0} promoted, ${data.rejected?.length || 0} rejected (${((data.duration_ms || 0) / 1000).toFixed(1)}s)`;
      break;
    default:
      if (data.message) {
        message = data.message;
      } else {
        return null; // Skip unknown events
      }
  }

  return [{ type, message }];
}

function LiveTab({ agent, skills, onRefresh }: { agent: Agent; skills: Skill[]; onRefresh: () => void }) {
  const [task, setTask] = useState("");
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [wsStatus, setWsStatus] = useState<"disconnected" | "connected" | "error">(
    "disconnected"
  );
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load persisted event history on mount
  useEffect(() => {
    fetch(`${window.location.origin}/api/agents/${agent.id}/events?limit=200`)
      .then(r => r.json())
      .then((history: any[]) => {
        const mapped = history.flatMap(e => formatWsEvent(e) || []);
        if (mapped.length > 0) {
          setEvents(mapped);
        }
      })
      .catch(() => {});
  }, [agent.id]);

  useEffect(() => {
    const ws = createLiveSocket(agent.id);
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("error");
    ws.onmessage = e => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "heartbeat") return;

        const formatted = formatWsEvent(data);
        if (formatted) {
          setEvents(prev => [...prev, ...formatted]);
        }

        // Refresh data on significant events
        if (["episode_end", "evolution_end", "skill_promoted"].includes(data.type)) {
          onRefresh();
        }
      } catch {
        setEvents(prev => [...prev, { type: "info", message: e.data }]);
      }
    };

    return () => {
      ws.close();
    };
  }, [agent.id]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  async function handleRun() {
    if (!task.trim()) return;
    setRunning(true);
    const currentTask = task;
    setTask("");
    setEvents(prev => [
      ...prev,
      { type: "info", message: `▶ Running task: ${currentTask}` },
    ]);
    try {
      await runTask(agent.id, currentTask);
      // Results come through WebSocket — just refresh data
      onRefresh();
    } catch {
      setEvents(prev => [
        ...prev,
        { type: "error", message: "Failed to submit task — is the backend running?" },
      ]);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex gap-4 h-full">
      {/* Main terminal area */}
      <div className="flex-1 flex flex-col gap-3 min-w-0">
        {/* Task input */}
        <div className="flex gap-2">
          <Input
            value={task}
            onChange={e => setTask(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !running && handleRun()}
            placeholder="Enter task description and press Run..."
            className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 font-mono text-sm flex-1"
          />
          <Button
            onClick={handleRun}
            disabled={running || !task.trim()}
            className="bg-emerald-600 hover:bg-emerald-500 text-white gap-1.5 shrink-0"
          >
            <Play size={13} /> Run
          </Button>
        </div>

        {/* Terminal */}
        <div className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col min-h-0">
          <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 shrink-0">
            <div className="flex items-center gap-2">
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
              </div>
              <span className="text-xs text-zinc-600 font-mono">live feed</span>
            </div>
            <span
              className={`text-[10px] font-mono ${
                wsStatus === "connected"
                  ? "text-emerald-500"
                  : wsStatus === "error"
                  ? "text-red-500"
                  : "text-zinc-600"
              }`}
            >
              ws:{wsStatus}
            </span>
          </div>

          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto p-3 font-mono text-xs space-y-1"
          >
            {events.length === 0 ? (
              <p className="text-zinc-700 italic">Waiting for events...</p>
            ) : (
              events.map((ev, i) => (
                <div key={i} className="flex gap-2 items-start">
                  {ev.ts && (
                    <span className="text-zinc-700 shrink-0">{ev.ts}</span>
                  )}
                  <span className={`shrink-0 ${eventColor(ev.type)}`}>
                    {eventPrefix(ev.type)}
                  </span>
                  <span className={eventColor(ev.type)}>{ev.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Right sidebar */}
      <div className="w-56 shrink-0 flex flex-col gap-3">
        {/* Stats */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2.5">
            Stats
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Skills</span>
              <span className="text-xs font-mono text-zinc-200">
                {agent.skills_count ?? 0}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Success rate</span>
              <span className="text-xs font-mono text-zinc-200">
                {agent.success_rate != null
                  ? `${Math.round(agent.success_rate * 100)}%`
                  : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-xs text-zinc-500">Episodes</span>
              <span className="text-xs font-mono text-zinc-200">
                {agent.episodes ?? 0}
              </span>
            </div>
          </div>
        </div>

        {/* Active skills */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex-1">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2.5">
            Active Skills
          </p>
          <div className="flex flex-col gap-1.5">
            {skills.filter(s => s.status === "active").length === 0 ? (
              <p className="text-xs text-zinc-700 italic">No active skills</p>
            ) : (
              skills
                .filter(s => s.status === "active")
                .slice(0, 8)
                .map(s => (
                  <div key={s.id} className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                    <Link
                      to={`/skills/${s.id}`}
                      className="text-xs text-zinc-400 hover:text-emerald-400 font-mono truncate transition-colors"
                    >
                      {s.name}
                    </Link>
                  </div>
                ))
            )}
          </div>
        </div>

        {/* Config summary */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2.5">
            Config
          </p>
          <div className="flex flex-col gap-1.5">
            <div>
              <span className="text-[10px] text-zinc-600">Model</span>
              <p className="text-xs font-mono text-zinc-300 truncate">{agent.model}</p>
            </div>
            {agent.sandbox_backend && (
              <div>
                <span className="text-[10px] text-zinc-600">Sandbox</span>
                <p className="text-xs font-mono text-zinc-300">{agent.sandbox_backend}</p>
              </div>
            )}
            {agent.reward_function && (
              <div>
                <span className="text-[10px] text-zinc-600">Reward fn</span>
                <p className="text-xs font-mono text-zinc-300">{agent.reward_function}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfigTab({ agent, onSave }: { agent: Agent; onSave: () => void }) {
  const [form, setForm] = useState({
    system_prompt: agent.system_prompt || "",
    reward_function: agent.reward_function || "task_success",
    failure_threshold: agent.failure_threshold || 5,
    sandbox_backend: agent.sandbox_backend || "subprocess",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await fetch(`${window.location.origin}/api/agents/${agent.id}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSave();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-6 max-w-2xl flex flex-col gap-5">
      <div>
        <label className="text-xs font-medium text-zinc-400 mb-1.5 block">System Prompt</label>
        <textarea
          className="w-full bg-zinc-900 border border-zinc-800 rounded-md p-3 text-sm text-zinc-200 font-mono min-h-[120px] focus:outline-none focus:border-zinc-600 resize-y"
          value={form.system_prompt}
          onChange={e => setForm({ ...form, system_prompt: e.target.value })}
        />
      </div>

      <div>
        <label className="text-xs font-medium text-zinc-400 mb-1.5 block">Reward Function</label>
        <div className="flex flex-col gap-2">
          {[
            { value: "task_success", label: "Task Success", desc: "Checks metadata signals (expected output, success flag). Falls back to 1.0 if no tool errors." },
            { value: "answer_match_reward", label: "Answer Match", desc: "Compares agent output against expected answer. 1.0 exact match, 0.7 substring, 0.0 no match." },
            { value: "code_execution_reward", label: "Code Execution", desc: "1.0 if no tool errors, minus 0.25 per error. Best for tool-heavy agents." },
            { value: "efficiency_reward", label: "Efficiency", desc: "Penalizes extra steps. 1.0 for 1 step, -0.1 per additional step." },
            { value: "llm_judge_reward", label: "LLM Judge", desc: "Uses an LLM to rate the response quality 0-1. Best for open-ended tasks. ~$0.001/call." },
          ].map(opt => (
            <label
              key={opt.value}
              className={`flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors ${
                form.reward_function === opt.value
                  ? "bg-zinc-800 border-zinc-600"
                  : "bg-zinc-900 border-zinc-800 hover:border-zinc-700"
              }`}
            >
              <input
                type="radio"
                name="reward"
                value={opt.value}
                checked={form.reward_function === opt.value}
                onChange={() => setForm({ ...form, reward_function: opt.value })}
                className="mt-1 accent-white"
              />
              <div>
                <div className="text-sm text-zinc-200 font-medium">{opt.label}</div>
                <div className="text-xs text-zinc-500 mt-0.5">{opt.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">

        <div>
          <label className="text-xs font-medium text-zinc-400 mb-1.5 block">Sandbox Backend</label>
          <select
            className="w-full bg-zinc-900 border border-zinc-800 rounded-md p-2 text-sm text-zinc-200 focus:outline-none focus:border-zinc-600"
            value={form.sandbox_backend}
            onChange={e => setForm({ ...form, sandbox_backend: e.target.value })}
          >
            <option value="subprocess">subprocess</option>
            <option value="docker">docker</option>
          </select>
        </div>
      </div>

      <div>
        <label className="text-xs font-medium text-zinc-400 mb-1.5 block">Failure Threshold</label>
        <Input
          type="number"
          className="w-32 bg-zinc-900 border-zinc-800"
          value={form.failure_threshold}
          onChange={e => setForm({ ...form, failure_threshold: parseInt(e.target.value) || 5 })}
        />
        <p className="text-xs text-zinc-600 mt-1">Consecutive failures before evolution triggers</p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Changes"}
        </Button>
        {saved && <span className="text-xs text-emerald-400">Saved! Agent will use new config on next run.</span>}
      </div>
    </div>
  );
}

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [evolutions, setEvolutions] = useState<Evolution[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("live");

  async function loadAgent() {
    if (!id) return;
    try {
      const [agentData, skillsData, trajData, evolData] = await Promise.allSettled([
        fetchAgent(id!),
        fetchSkills(id!),
        fetchTrajectories(id!),
        fetchEvolutions(id!),
      ]);
      if (agentData.status === "fulfilled") setAgent(agentData.value);
      if (skillsData.status === "fulfilled")
        setSkills(Array.isArray(skillsData.value) ? skillsData.value : []);
      if (trajData.status === "fulfilled")
        setTrajectories(Array.isArray(trajData.value) ? trajData.value : []);
      if (evolData.status === "fulfilled")
        setEvolutions(Array.isArray(evolData.value) ? evolData.value : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAgent();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Loading agent...
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-zinc-400">Agent not found</p>
        <Link to="/" className="text-sm text-emerald-400 hover:underline">
          ← Back to agents
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2 mb-3">
          <Link
            to="/"
            className="text-xs text-zinc-600 hover:text-zinc-400 flex items-center gap-1 transition-colors"
          >
            <ChevronLeft size={12} /> Agents
          </Link>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-zinc-100">{agent.name}</h1>
            <StatusBadge status={agent.status} />
            <span className="text-sm text-zinc-500 font-mono">{agent.model}</span>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="border-zinc-700 text-zinc-400 hover:text-zinc-200 gap-1.5"
              onClick={() => setActiveTab("config")}
            >
              <Settings2 size={13} /> Config
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-zinc-700 text-zinc-400 hover:text-red-400 hover:border-red-900 gap-1.5"
            >
              <Square size={13} /> Stop
            </Button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex-1 overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <div className="px-6 pt-3 border-b border-zinc-800 shrink-0">
            <TabsList className="bg-transparent border-0 p-0 gap-0 h-auto">
              {["live", "skills", "trajectories", "evolution", "config"].map(t => (
                <TabsTrigger
                  key={t}
                  value={t}
                  className="capitalize px-4 py-2.5 rounded-none border-b-2 border-transparent text-zinc-500 data-[state=active]:border-emerald-500 data-[state=active]:text-zinc-100 data-[state=active]:bg-transparent hover:text-zinc-300 text-sm font-medium transition-colors"
                >
                  {t}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          <div className="flex-1 overflow-hidden">
            {/* Live */}
            <TabsContent value="live" className="h-full m-0 p-6 overflow-hidden flex flex-col">
              <LiveTab agent={agent} skills={skills} onRefresh={loadAgent} />
            </TabsContent>

            {/* Skills */}
            <TabsContent value="skills" className="h-full m-0 overflow-y-auto">
              <div className="p-6">
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      <TableHead className="text-zinc-500">Name</TableHead>
                      <TableHead className="text-zinc-500">Status</TableHead>
                      <TableHead className="text-zinc-500">Success Rate</TableHead>
                      <TableHead className="text-zinc-500">Invocations</TableHead>
                      <TableHead className="text-zinc-500">Origin</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {skills.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-zinc-600 py-8">
                          No skills yet
                        </TableCell>
                      </TableRow>
                    ) : (
                      skills.map(skill => (
                        <TableRow
                          key={skill.id}
                          className="border-zinc-800 hover:bg-zinc-900/50"
                        >
                          <TableCell>
                            <Link
                              to={`/skills/${skill.id}`}
                              className="font-mono text-sm text-emerald-400 hover:text-emerald-300 hover:underline"
                            >
                              {skill.name}
                            </Link>
                          </TableCell>
                          <TableCell>{skillStatusBadge(skill.status)}</TableCell>
                          <TableCell className="font-mono text-sm text-zinc-300">
                            {skill.success_rate != null
                              ? `${Math.round(skill.success_rate * 100)}%`
                              : "—"}
                          </TableCell>
                          <TableCell className="font-mono text-sm text-zinc-300">
                            {skill.invocations ?? 0}
                          </TableCell>
                          <TableCell className="text-xs text-zinc-500">
                            {skill.origin ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            {/* Trajectories */}
            <TabsContent value="trajectories" className="h-full m-0 overflow-y-auto">
              <div className="p-6">
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      <TableHead className="text-zinc-500">Episode</TableHead>
                      <TableHead className="text-zinc-500">Task</TableHead>
                      <TableHead className="text-zinc-500">Status</TableHead>
                      <TableHead className="text-zinc-500">Reward</TableHead>
                      <TableHead className="text-zinc-500">Steps</TableHead>
                      <TableHead className="text-zinc-500">Time</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {trajectories.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-center text-zinc-600 py-8">
                          No trajectories yet
                        </TableCell>
                      </TableRow>
                    ) : (
                      trajectories.map((t, i) => (
                        <TableRow
                          key={i}
                          className="border-zinc-800 hover:bg-zinc-900/50"
                        >
                          <TableCell className="font-mono text-sm text-zinc-400">
                            #{trajectories.length - i}
                          </TableCell>
                          <TableCell className="text-sm text-zinc-300 max-w-[240px] truncate">
                            {t.task}
                          </TableCell>
                          <TableCell>{trajectoryStatusBadge(t.status)}</TableCell>
                          <TableCell className="font-mono text-sm text-zinc-300">
                            {t.reward.toFixed(2)}
                          </TableCell>
                          <TableCell className="font-mono text-sm text-zinc-400">
                            {t.steps_count}
                          </TableCell>
                          <TableCell className="font-mono text-sm text-zinc-400">
                            {new Date(t.timestamp).toLocaleTimeString()}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            {/* Evolution */}
            <TabsContent value="evolution" className="h-full m-0 overflow-y-auto">
              <div className="p-6 flex flex-col gap-3">
                {evolutions.length === 0 ? (
                  <p className="text-zinc-600 text-sm text-center py-8">No evolution events yet</p>
                ) : (
                  evolutions.map((ev, i) => (
                    <div
                      key={i}
                      className="bg-zinc-900 border border-zinc-800 rounded-lg p-4"
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <Badge className="bg-amber-950 text-amber-400 border-0">Evolution</Badge>
                        <span className="text-xs font-mono text-zinc-500">
                          {new Date(ev.timestamp).toLocaleString()}
                        </span>
                        <span className="text-xs text-zinc-600">
                          {(ev.duration_ms / 1000).toFixed(1)}s
                        </span>
                      </div>
                      {ev.gaps_detected.length > 0 && (
                        <div className="mb-2">
                          <span className="text-xs text-zinc-500">Gaps: </span>
                          <span className="text-xs text-amber-400">{ev.gaps_detected.join(", ")}</span>
                        </div>
                      )}
                      {ev.tools_promoted.length > 0 && (
                        <div className="mb-2">
                          <span className="text-xs text-zinc-500">Promoted: </span>
                          {ev.tools_promoted.map(name => (
                            <span key={name} className="text-xs font-mono text-emerald-400 mr-2">{name}</span>
                          ))}
                        </div>
                      )}
                      {ev.tools_rejected.length > 0 && (
                        <div>
                          <span className="text-xs text-zinc-500">Rejected: </span>
                          {ev.tools_rejected.map((r, j) => (
                            <span key={j} className="text-xs font-mono text-red-400 mr-2">
                              {typeof r === 'string' ? r : `${r.name} (${r.reason})`}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </TabsContent>

            {/* Config */}
            <TabsContent value="config" className="h-full m-0 overflow-y-auto">
              <ConfigTab agent={agent} onSave={loadAgent} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}
