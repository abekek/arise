"""ARISE benchmark runner — evaluates ARISE vs baselines on AcmeCorp tasks.

Usage:
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --no-evolution
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --fixed-tools
    python benchmarks/run_benchmark.py --model gpt-4o-mini --seed 42 --quick
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ARISE benchmark suite against AcmeCorp tasks."
    )
    parser.add_argument(
        "--model",
        required=True,
        help="LLM model name for litellm (e.g. gpt-4o-mini)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for deterministic environment generation (default: 42)",
    )
    parser.add_argument(
        "--no-evolution",
        action="store_true",
        default=False,
        help="Disable ARISE; agent gets no tools at all",
    )
    parser.add_argument(
        "--fixed-tools",
        action="store_true",
        default=False,
        help="Agent starts with hand-written baseline tools; evolution disabled",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        default=False,
        help="Quick mode: run only easy tasks (~20) instead of all 60",
    )
    parser.add_argument(
        "--output-dir",
        default="benchmarks/results/",
        help="Directory for JSON results (default: benchmarks/results/)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Agent function
# ---------------------------------------------------------------------------


def create_agent_fn(model: str):
    """Create an agent function that uses litellm for reasoning + tool calling."""

    def agent_fn(task: str, tools: list) -> str:
        import json as _json

        import litellm

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an SRE agent at AcmeCorp. "
                    "Use available tools to complete tasks. "
                    "Return concise, precise answers."
                ),
            },
            {"role": "user", "content": task},
        ]

        # Convert ToolSpec objects to OpenAI function-calling format
        openai_tools = []
        tool_map: dict[str, Any] = {}
        for t in tools:
            tool_map[t.name] = t
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters
                        or {"type": "object", "properties": {}},
                    },
                }
            )

        for _ in range(10):  # max 10 tool-call rounds
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": 0,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools

            response = litellm.completion(**kwargs)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = (
                        _json.loads(tc.function.arguments)
                        if tc.function.arguments
                        else {}
                    )
                    if fn_name in tool_map:
                        try:
                            result = tool_map[fn_name](**fn_args)
                        except Exception as exc:
                            result = f"Error: {exc}"
                    else:
                        result = f"Unknown tool: {fn_name}"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result),
                        }
                    )
            else:
                return choice.message.content or ""

        return "Max tool call rounds exceeded"

    return agent_fn


# ---------------------------------------------------------------------------
# Reward function (mutable closure via module-level state)
# ---------------------------------------------------------------------------

# These are set just before each arise.run() / agent.run() call so the
# reward function can reference the current episode's check function and env.
_current_task_check = None
_current_env = None


def benchmark_reward(trajectory) -> float:
    """Return 1.0 if the task check passes on the trajectory outcome, else 0.0."""
    if _current_task_check is not None and _current_env is not None:
        try:
            return 1.0 if _current_task_check(trajectory.outcome, _current_env) else 0.0
        except Exception:
            return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Baseline agent wrappers
# ---------------------------------------------------------------------------


class NoEvolutionAgent:
    """Calls the agent with no tools — pure LLM, no ARISE."""

    def __init__(self, agent_fn):
        self._agent_fn = agent_fn

    def run(self, task: str, **kwargs) -> str:
        return self._agent_fn(task, [])


class FixedToolsAgent:
    """Calls the agent with a fixed pre-defined tool set; never evolves."""

    def __init__(self, agent_fn, tools: list):
        self._agent_fn = agent_fn
        self._tools = tools

    def run(self, task: str, **kwargs) -> str:
        return self._agent_fn(task, self._tools)


# ---------------------------------------------------------------------------
# Episode runner
# ---------------------------------------------------------------------------


def run_episode(
    episode_number: int,
    task_def: dict,
    agent,  # ARISE instance, NoEvolutionAgent, or FixedToolsAgent
    env,
) -> dict:
    """Run a single benchmark episode and return a result dict."""
    global _current_task_check, _current_env

    task_str = task_def["task"]
    task_id = task_def.get("id", f"task-{episode_number:03d}")
    phase = task_def.get("phase", 0)

    # Wire up the reward function for this episode
    _current_task_check = task_def.get("check")
    _current_env = env

    start_ms = time.monotonic() * 1000

    try:
        outcome = agent.run(task_str)
    except Exception as exc:
        outcome = f"Error: {exc}"

    elapsed_ms = int(time.monotonic() * 1000 - start_ms)

    # Evaluate success using the check function
    success = False
    if _current_task_check is not None:
        try:
            success = bool(_current_task_check(outcome, env))
        except Exception:
            success = False

    # Count active skills if the agent is an ARISE instance
    skills_count = 0
    if hasattr(agent, "skills"):
        try:
            skills_count = len(agent.skills)
        except Exception:
            skills_count = 0

    return {
        "episode": episode_number,
        "phase": phase,
        "task_id": task_id,
        "task": task_str[:200],
        "success": success,
        "reward": 1.0 if success else 0.0,
        "skills_count": skills_count,
        "latency_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def compute_summary(results: list[dict], agent) -> dict:
    total = len(results)
    if total == 0:
        return {}

    successes = sum(1 for r in results if r["success"])
    total_success_rate = round(successes / total, 4)

    # Per-phase breakdown
    phase_totals: dict[str, int] = {}
    phase_successes: dict[str, int] = {}
    for r in results:
        key = str(r["phase"])
        phase_totals[key] = phase_totals.get(key, 0) + 1
        if r["success"]:
            phase_successes[key] = phase_successes.get(key, 0) + 1

    phase_success_rates = {
        phase: round(phase_successes.get(phase, 0) / total_count, 4)
        for phase, total_count in phase_totals.items()
    }

    # Final skill count
    total_skills = 0
    if hasattr(agent, "skills"):
        try:
            total_skills = len(agent.skills)
        except Exception:
            total_skills = 0

    return {
        "total_success_rate": total_success_rate,
        "phase_success_rates": phase_success_rates,
        "total_skills": total_skills,
        "total_episodes": total,
    }


def print_episode_summary(episode: dict) -> None:
    status = "PASS" if episode["success"] else "FAIL"
    print(
        f"  [{status}] Episode {episode['episode']:3d} | "
        f"Phase {episode['phase']} | "
        f"{episode['task_id']:10s} | "
        f"{episode['latency_ms']:5d}ms | "
        f"skills={episode['skills_count']}"
    )


def print_final_summary(summary: dict, mode: str, model: str) -> None:
    print()
    print("=" * 60)
    print(f"  ARISE Benchmark Results")
    print(f"  Model : {model}")
    print(f"  Mode  : {mode}")
    print("=" * 60)
    print(f"  Total episodes : {summary.get('total_episodes', 0)}")
    print(f"  Overall success: {summary.get('total_success_rate', 0):.1%}")
    print()
    print("  Per-phase success rates:")
    for phase, rate in sorted(summary.get("phase_success_rates", {}).items()):
        print(f"    Phase {phase}: {rate:.1%}")
    print(f"  Final skill count: {summary.get('total_skills', 0)}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Results writer
# ---------------------------------------------------------------------------


def write_results(
    results: list[dict],
    args: argparse.Namespace,
    summary: dict,
    output_dir: str,
) -> str:
    """Write results JSON to output_dir and return the file path."""
    mode = _mode_label(args)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{args.model}_{mode}_{args.seed}_{timestamp}.json".replace("/", "-")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)

    payload = {
        "model": args.model,
        "mode": mode,
        "seed": args.seed,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "episodes": results,
        "summary": summary,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Results written to: {path}")
    return path


def _mode_label(args: argparse.Namespace) -> str:
    if args.no_evolution:
        return "no_evolution"
    if args.fixed_tools:
        return "fixed_tools"
    return "arise"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()

    # Ensure project root is on sys.path so `arise` and `benchmarks` are importable
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from arise import ARISE, ARISEConfig
    from benchmarks.acmecorp.fixtures import generate
    from benchmarks.acmecorp.metrics import create_metrics_app, start_metrics_server, stop_metrics_server
    from benchmarks.tasks import get_all_tasks, get_quick_tasks

    print(f"[benchmark] Generating AcmeCorp environment (seed={args.seed})...")
    env = generate(seed=args.seed)

    print(f"[benchmark] Starting metrics mock server on port {env.metrics_port}...")
    app = create_metrics_app(env.metrics_data)
    server_thread = start_metrics_server(app, port=env.metrics_port)

    # Build the core LLM agent function
    agent_fn = create_agent_fn(args.model)

    # Initialise agent / ARISE based on mode
    mode = _mode_label(args)
    print(f"[benchmark] Mode: {mode}")

    if args.no_evolution:
        agent = NoEvolutionAgent(agent_fn)

    elif args.fixed_tools:
        from benchmarks.baselines.fixed_tools import get_fixed_tools
        tools = get_fixed_tools()
        agent = FixedToolsAgent(agent_fn, tools)

    else:
        # Full ARISE with evolution enabled
        agent = ARISE(
            agent_fn=agent_fn,
            reward_fn=benchmark_reward,
            config=ARISEConfig(
                model=args.model,
                failure_threshold=3,        # trigger evolution quickly during benchmarks
                max_evolutions_per_hour=20,  # don't rate-limit during benchmark run
                verbose=True,
            ),
        )

    # Select task set
    tasks = get_quick_tasks(env) if args.quick else get_all_tasks(env)
    print(f"[benchmark] Running {len(tasks)} episodes...")
    print()

    results: list[dict] = []
    for i, task_def in enumerate(tasks):
        episode = run_episode(i + 1, task_def, agent, env)
        results.append(episode)
        print_episode_summary(episode)

    # Compute and display summary
    summary = compute_summary(results, agent)
    print_final_summary(summary, mode, args.model)

    # Persist results
    write_results(results, args, summary, args.output_dir)

    # Cleanup
    print("[benchmark] Stopping metrics server...")
    stop_metrics_server(server_thread)
    env.cleanup()
    print("[benchmark] Done.")


if __name__ == "__main__":
    main()
