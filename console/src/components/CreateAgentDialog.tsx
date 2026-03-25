import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createAgent } from "@/lib/api";
import { Plus, Trash2 } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const MODELS = [
  "claude-opus-4-5",
  "claude-sonnet-4-5",
  "gpt-4o",
  "gpt-4-turbo",
  "gemini-1.5-pro",
];

const REWARD_FNS = [
  "task_completion",
  "code_correctness",
  "efficiency",
  "custom",
];

const SANDBOX_BACKENDS = ["docker", "e2b", "modal", "local"];

export default function CreateAgentDialog({ open, onClose }: Props) {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [model, setModel] = useState(MODELS[0]);
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a capable agent. Use available skills to complete tasks efficiently."
  );
  const [tasks, setTasks] = useState<string[]>([""]);
  const [rewardFn, setRewardFn] = useState(REWARD_FNS[0]);
  const [allowedImports, setAllowedImports] = useState("os, sys, json, re");
  const [sandbox, setSandbox] = useState(SANDBOX_BACKENDS[0]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  function addTask() {
    setTasks(t => [...t, ""]);
  }

  function removeTask(i: number) {
    setTasks(t => t.filter((_, idx) => idx !== i));
  }

  function setTask(i: number, val: string) {
    setTasks(t => t.map((v, idx) => (idx === i ? val : v)));
  }

  async function handleCreate() {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setError("");
    setCreating(true);
    try {
      const result = await createAgent({
        name: name.trim(),
        model,
        system_prompt: systemPrompt,
        tasks: tasks.filter(t => t.trim()),
        reward_function: rewardFn,
        allowed_imports: allowedImports
          .split(",")
          .map(s => s.trim())
          .filter(Boolean),
        sandbox_backend: sandbox,
      });
      onClose();
      if (result?.id) {
        navigate(`/agents/${result.id}`);
      }
    } catch (e) {
      setError("Failed to create agent. Is the backend running?");
    } finally {
      setCreating(false);
    }
  }

  const labelClass = "block text-xs font-medium text-zinc-400 mb-1";
  const selectClass =
    "w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-sm rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-zinc-500";

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-zinc-100 text-lg">Create New Agent</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-5 py-2">
          {/* Name */}
          <div>
            <label className={labelClass}>Name</label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. code-solver-v1"
              className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600"
            />
          </div>

          {/* Model */}
          <div>
            <label className={labelClass}>Model</label>
            <select value={model} onChange={e => setModel(e.target.value)} className={selectClass}>
              {MODELS.map(m => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* System Prompt */}
          <div>
            <label className={labelClass}>System Prompt</label>
            <textarea
              value={systemPrompt}
              onChange={e => setSystemPrompt(e.target.value)}
              rows={3}
              className="w-full bg-zinc-900 border border-zinc-700 text-zinc-200 text-sm rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-zinc-500 resize-none font-mono"
            />
          </div>

          {/* Tasks */}
          <div>
            <label className={labelClass}>Training Tasks</label>
            <div className="flex flex-col gap-2">
              {tasks.map((task, i) => (
                <div key={i} className="flex gap-2">
                  <Input
                    value={task}
                    onChange={e => setTask(i, e.target.value)}
                    placeholder={`Task ${i + 1}`}
                    className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 flex-1"
                  />
                  {tasks.length > 1 && (
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => removeTask(i)}
                      className="text-zinc-500 hover:text-red-400 shrink-0"
                    >
                      <Trash2 size={14} />
                    </Button>
                  )}
                </div>
              ))}
              <Button
                variant="ghost"
                size="sm"
                onClick={addTask}
                className="self-start text-zinc-500 hover:text-zinc-300 gap-1.5"
              >
                <Plus size={13} /> Add Task
              </Button>
            </div>
          </div>

          {/* Reward Function */}
          <div>
            <label className={labelClass}>Reward Function</label>
            <select
              value={rewardFn}
              onChange={e => setRewardFn(e.target.value)}
              className={selectClass}
            >
              {REWARD_FNS.map(r => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {/* Allowed Imports */}
          <div>
            <label className={labelClass}>Allowed Imports (comma-separated)</label>
            <Input
              value={allowedImports}
              onChange={e => setAllowedImports(e.target.value)}
              placeholder="os, sys, json"
              className="bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600 font-mono text-sm"
            />
          </div>

          {/* Sandbox */}
          <div>
            <label className={labelClass}>Sandbox Backend</label>
            <select
              value={sandbox}
              onChange={e => setSandbox(e.target.value)}
              className={selectClass}
            >
              {SANDBOX_BACKENDS.map(s => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-200"
          >
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={creating}
            className="bg-emerald-600 hover:bg-emerald-500 text-white"
          >
            {creating ? "Creating..." : "Create Agent"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
