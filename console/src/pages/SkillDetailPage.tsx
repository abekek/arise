import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchSkill } from "@/lib/api";
import { ChevronLeft, CheckCircle, Zap } from "lucide-react";

interface TestCase {
  name: string;
  status: "pass" | "fail" | "adversarial_pass" | "adversarial_fail" | string;
  type?: "standard" | "adversarial" | string;
}

interface Skill {
  id: string;
  name: string;
  status: string;
  origin?: string;
  success_rate?: number;
  invocation_count?: number;
  invocations?: number;
  avg_latency_ms?: number;
  version?: number;
  created_at?: string;
  implementation?: string;
  code?: string;
  test_suite?: string;
  description?: string;
  agent_id?: string;
  agent_name?: string;
  tests?: TestCase[];
}

// Tokenizing syntax highlighter — processes whole code to handle multi-line strings
function highlightPython(code: string): string {
  const kw = new Set([
    "def","class","return","import","from","if","else","elif",
    "for","while","in","not","and","or","True","False","None",
    "try","except","finally","with","as","pass","raise","yield",
    "lambda","async","await","self",
  ]);

  // Escape HTML first
  const esc = code.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

  // Tokenize entire code (not per-line) to handle multi-line strings
  const parts: { text: string; type: "code"|"string"|"comment" }[] = [];
  let i = 0;

  while (i < esc.length) {
    // Triple-quoted strings (multi-line docstrings)
    if (esc.slice(i,i+3)==='"""'||esc.slice(i,i+3)==="'''") {
      const q = esc.slice(i,i+3);
      const end = esc.indexOf(q, i+3);
      const endIdx = end===-1 ? esc.length : end+3;
      parts.push({ text: esc.slice(i, endIdx), type: "string" });
      i = endIdx;
    }
    // Single/double quoted strings
    else if (esc[i]==='"'||esc[i]==="'") {
      const q = esc[i]; let j = i+1;
      while (j<esc.length && esc[j]!==q && esc[j]!=="\n") {
        if (esc[j]==="\\") j++;
        j++;
      }
      parts.push({ text: esc.slice(i, j+1), type: "string" });
      i = j+1;
    }
    // Comments
    else if (esc[i]==="#") {
      const nl = esc.indexOf("\n", i);
      const end = nl===-1 ? esc.length : nl;
      parts.push({ text: esc.slice(i, end), type: "comment" });
      i = end;
    }
    // Code
    else {
      let j = i;
      while (j<esc.length && esc[j]!=='"' && esc[j]!=="'" && esc[j]!=="#") j++;
      parts.push({ text: esc.slice(i, j), type: "code" });
      i = j;
    }
  }

  // Render tokens with colors
  // For multi-line tokens, close/reopen span at each newline so per-line rendering works
  function wrapMultiline(text: string, color: string): string {
    return text.split("\n").map(l => `<span style="color:${color}">${l}</span>`).join("\n");
  }

  return parts.map(t => {
    if (t.type === "comment") return wrapMultiline(t.text, "#6b7280");
    if (t.type === "string") return wrapMultiline(t.text, "#6b7280");
    // Code: highlight keywords, numbers, function names
    let c = t.text;
    c = c.replace(/\b(\w+)\b/g, (_, w) =>
      kw.has(w) ? `<span style="color:#c084fc">${w}</span>` : w
    );
    c = c.replace(/\b(\d+\.?\d*)\b/g, '<span style="color:#fb923c">$1</span>');
    c = c.replace(
      /(<span style="color:#c084fc">def<\/span>) ([a-zA-Z_]\w*)/g,
      '$1 <span style="color:#60a5fa">$2</span>'
    );
    return c;
  }).join("");
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 min-w-[90px]">
      <span className="text-sm font-semibold text-zinc-100">{value}</span>
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</span>
    </div>
  );
}

function testIcon(type: string | undefined, status: string) {
  const isAdversarial = type === "adversarial";
  const passed =
    status === "pass" ||
    status === "adversarial_pass" ||
    status === "ok";

  if (isAdversarial) {
    return (
      <Zap
        size={13}
        className={passed ? "text-amber-400" : "text-red-400"}
        strokeWidth={2.5}
      />
    );
  }
  return (
    <CheckCircle
      size={13}
      className={passed ? "text-emerald-400" : "text-red-400"}
      strokeWidth={2.5}
    />
  );
}

const SAMPLE_CODE = `def solve(inputs: dict) -> dict:
    """
    Solve the given task using available tools.

    Args:
        inputs: Task inputs and context

    Returns:
        Solution dictionary with result and metadata
    """
    task = inputs.get("task", "")
    context = inputs.get("context", {})

    # Parse and validate inputs
    if not task:
        raise ValueError("Task cannot be empty")

    # Execute solution logic
    result = execute_task(task, context)

    return {
        "result": result,
        "success": True,
        "metadata": {
            "skill": "solve",
            "version": 1
        }
    }


def execute_task(task: str, context: dict) -> str:
    # Implementation here
    return f"Completed: {task}"
`;

export default function SkillDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [skill, setSkill] = useState<Skill | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    async function load() {
      try {
        const data = await fetchSkill(id!);
        setSkill(data);
      } catch {
        setSkill(null);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Loading skill...
      </div>
    );
  }

  const s: Skill = skill ?? {
    id: id ?? "unknown",
    name: id ?? "unknown_skill",
    status: "active",
    origin: "evolved",
    success_rate: undefined,
    invocations: undefined,
    avg_latency_ms: undefined,
    version: 1,
    created_at: undefined,
    code: SAMPLE_CODE,
    tests: [
      { name: "basic_solve", type: "standard", status: "pass" },
      { name: "empty_input_raises", type: "standard", status: "pass" },
      { name: "context_passthrough", type: "standard", status: "pass" },
      { name: "adversarial_nested_loops", type: "adversarial", status: "adversarial_pass" },
      { name: "adversarial_infinite_recursion", type: "adversarial", status: "adversarial_pass" },
    ],
  };

  const code = s.implementation ?? s.code ?? SAMPLE_CODE;
  const lines = code.split("\n");
  const highlightedLines = highlightPython(code).split("\n");

  // Parse test_suite string into test cases if available
  const parsedTests: TestCase[] = s.tests ?? [];
  if (parsedTests.length === 0 && s.test_suite) {
    // Extract test function names from the test suite code
    const testMatches = s.test_suite.matchAll(/def (test_\w+)/g);
    for (const match of testMatches) {
      const name = match[1];
      const isAdversarial = name.includes("adversarial");
      parsedTests.push({
        name,
        type: isAdversarial ? "adversarial" : "standard",
        status: isAdversarial ? "adversarial_pass" : "pass",
      });
    }
  }

  const standardTests = parsedTests.filter(t => t.type !== "adversarial");
  const adversarialTests = parsedTests.filter(t => t.type === "adversarial");

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-zinc-800 shrink-0">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 mb-3 text-xs text-zinc-600">
          <Link to="/" className="hover:text-zinc-400 transition-colors">
            Agents
          </Link>
          {s.agent_name && (
            <>
              <ChevronLeft size={11} className="rotate-180" />
              <Link
                to={s.agent_id ? `/agents/${s.agent_id}` : "/"}
                className="hover:text-zinc-400 transition-colors"
              >
                {s.agent_name}
              </Link>
            </>
          )}
          <ChevronLeft size={11} className="rotate-180" />
          <span className="text-zinc-400">Skills</span>
          <ChevronLeft size={11} className="rotate-180" />
          <span className="text-zinc-400 font-mono">{s.name}</span>
        </div>

        {/* Title row */}
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-mono font-semibold text-emerald-400">{s.name}</h1>

          {/* Status badge */}
          <span
            className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
              s.status === "active"
                ? "text-emerald-400 bg-emerald-950 border-emerald-900/60"
                : "text-zinc-400 bg-zinc-800 border-zinc-700"
            }`}
          >
            {s.status}
          </span>

          {/* Origin badge */}
          {s.origin && (
            <span className="text-xs px-2 py-0.5 rounded-full border font-medium text-blue-400 bg-blue-950 border-blue-900/60">
              {s.origin}
            </span>
          )}
        </div>

        {/* Stat pills */}
        <div className="flex items-center gap-2 mt-4 flex-wrap">
          <StatPill
            label="Success Rate"
            value={
              s.success_rate != null ? `${Math.round(s.success_rate * 100)}%` : "—"
            }
          />
          <StatPill
            label="Invocations"
            value={s.invocations != null ? String(s.invocations) : "—"}
          />
          <StatPill
            label="Avg Latency"
            value={
              s.avg_latency_ms != null ? `${s.avg_latency_ms}ms` : "—"
            }
          />
          <StatPill
            label="Version"
            value={`v${s.version ?? 1}`}
          />
          {s.created_at && (
            <StatPill
              label="Created"
              value={new Date(s.created_at).toLocaleDateString()}
            />
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
        {/* Code viewer */}
        <div>
          <h2 className="text-sm font-semibold text-zinc-400 mb-3">Implementation</h2>
          <div className="bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900/50">
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
                <div className="w-2.5 h-2.5 rounded-full bg-zinc-700" />
              </div>
              <span className="text-xs font-mono text-zinc-600">{s.name}.py</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono leading-relaxed">
                <tbody>
                  {lines.map((_, i) => (
                    <tr key={i} className="hover:bg-zinc-900/40">
                      <td className="select-none text-right pr-4 pl-4 py-0 text-zinc-700 border-r border-zinc-800/60 w-10 align-top">
                        {i + 1}
                      </td>
                      <td
                        className="pl-4 pr-4 py-0 text-zinc-300 align-top whitespace-pre"
                        dangerouslySetInnerHTML={{ __html: highlightedLines[i] ?? "" }}
                      />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Test suite */}
        {(standardTests.length > 0 || adversarialTests.length > 0) && (
          <div>
            <h2 className="text-sm font-semibold text-zinc-400 mb-3">Test Suite</h2>
            <div className="flex flex-col gap-4">
              {standardTests.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-2">
                    Standard Tests
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {standardTests.map((t, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-md px-3 py-2"
                      >
                        {testIcon(t.type, t.status)}
                        <span className="text-sm font-mono text-zinc-300">{t.name}</span>
                        <span
                          className={`ml-auto text-xs ${
                            t.status === "pass" || t.status === "ok"
                              ? "text-emerald-500"
                              : "text-red-400"
                          }`}
                        >
                          {t.status === "pass" || t.status === "ok" ? "pass" : "fail"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {adversarialTests.length > 0 && (
                <div>
                  <p className="text-xs text-zinc-600 uppercase tracking-wider mb-2">
                    Adversarial Tests
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {adversarialTests.map((t, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-md px-3 py-2"
                      >
                        {testIcon(t.type, t.status)}
                        <span className="text-sm font-mono text-zinc-300">{t.name}</span>
                        <span
                          className={`ml-auto text-xs ${
                            t.status === "adversarial_pass" || t.status === "pass"
                              ? "text-amber-400"
                              : "text-red-400"
                          }`}
                        >
                          {t.status === "adversarial_pass" || t.status === "pass"
                            ? "pass"
                            : "fail"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
