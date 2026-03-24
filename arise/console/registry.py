import json
import os
import uuid
from datetime import datetime
from typing import Any

from arise import ARISE, ARISEConfig
from arise.rewards.builtin import task_success, code_execution_reward, answer_match_reward, efficiency_reward
from arise.skills.library import SkillLibrary
from arise.skills.sandbox import Sandbox
from arise.trajectory.store import TrajectoryStore

from .schemas import AgentCreate, AgentUpdate

REWARD_PRESETS = {
    "task_success": task_success,
    "code_execution_reward": code_execution_reward,
    "answer_match_reward": answer_match_reward,
    "efficiency_reward": efficiency_reward,
}


class AgentRegistry:
    """Manages ARISE agent instances in-memory with JSON persistence."""

    def __init__(self, data_dir: str = "~/.arise/console"):
        self.data_dir = os.path.expanduser(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self._config_path = os.path.join(self.data_dir, "agents.json")
        self._agents: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Load agent configs from disk (not ARISE instances -- those are created on demand)."""
        if os.path.exists(self._config_path):
            with open(self._config_path) as f:
                configs = json.load(f)
            for agent_id, cfg in configs.items():
                self._agents[agent_id] = {
                    **cfg,
                    "arise": None,  # lazy init
                    "status": "stopped",
                }

    def _save(self):
        """Persist agent configs (without ARISE instances)."""
        configs = {}
        for agent_id, agent in self._agents.items():
            configs[agent_id] = {
                k: v for k, v in agent.items()
                if k not in ("arise", "status")
            }
        with open(self._config_path, "w") as f:
            json.dump(configs, f, indent=2, default=str)

    def create(self, req: AgentCreate) -> dict:
        agent_id = str(uuid.uuid4())[:8]
        agent_dir = os.path.join(self.data_dir, "agents", agent_id)
        os.makedirs(agent_dir, exist_ok=True)

        agent = {
            "id": agent_id,
            "name": req.name,
            "model": req.model,
            "system_prompt": req.system_prompt,
            "tasks": req.tasks,
            "reward_function": req.reward_function,
            "allowed_imports": req.allowed_imports,
            "sandbox_backend": req.sandbox_backend,
            "failure_threshold": req.failure_threshold,
            "api_key": req.api_key,
            "aws_profile": req.aws_profile,
            "aws_region": req.aws_region,
            "created_at": datetime.now().isoformat(),
            "skills_path": os.path.join(agent_dir, "skills"),
            "trajectories_path": os.path.join(agent_dir, "trajectories"),
            "arise": None,
            "status": "stopped",
        }
        self._agents[agent_id] = agent
        self._save()
        return self._summarize(agent)

    def list(self) -> list[dict]:
        return [self._summarize(a) for a in self._agents.values()]

    def get(self, agent_id: str) -> dict | None:
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        return self._detail(agent)

    def delete(self, agent_id: str):
        agent = self._agents.pop(agent_id, None)
        if agent and agent.get("arise"):
            # Clean up ARISE instance
            pass
        self._save()

    def update(self, agent_id: str, req: AgentUpdate) -> dict | None:
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        for field, value in req.model_dump(exclude_none=True).items():
            agent[field] = value
        self._save()
        return self._detail(agent)

    def get_arise(self, agent_id: str) -> ARISE | None:
        """Get or create the ARISE instance for an agent."""
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        if agent["arise"] is None:
            agent["arise"] = self._create_arise(agent)
            agent["status"] = "running"
        return agent["arise"]

    def set_status(self, agent_id: str, status: str):
        if agent_id in self._agents:
            self._agents[agent_id]["status"] = status

    def _create_arise(self, agent: dict) -> ARISE:
        config = ARISEConfig(
            model=agent["model"],
            sandbox_backend=agent["sandbox_backend"],
            failure_threshold=agent["failure_threshold"],
            allowed_imports=agent["allowed_imports"],
            skill_store_path=agent["skills_path"],
            trajectory_store_path=agent["trajectories_path"],
            verbose=False,
        )

        # Set API key in environment if provided
        if agent.get("api_key"):
            if "anthropic" in agent["model"].lower() or "bedrock" in agent["model"].lower():
                os.environ.setdefault("ANTHROPIC_API_KEY", agent["api_key"])
            else:
                os.environ.setdefault("OPENAI_API_KEY", agent["api_key"])

        reward_fn = REWARD_PRESETS.get(agent["reward_function"], task_success)

        # Create a simple agent_fn that uses litellm
        def agent_fn(task: str, tools: list) -> str:
            import litellm, json as _json
            tool_map = {t.name: t.fn for t in tools}
            tool_defs = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
            messages = [{"role": "user", "content": task}]
            system = agent.get("system_prompt", "You are a helpful assistant.")

            for _ in range(5):
                resp = litellm.completion(
                    model=agent["model"], messages=messages,
                    tools=tool_defs if tool_defs else None,
                    system=system, max_tokens=4096,
                )
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    return msg.content or ""
                messages.append(msg)
                for tc in msg.tool_calls:
                    fn = tool_map.get(tc.function.name)
                    if fn is None:
                        result = f"Error: tool '{tc.function.name}' not found"
                    else:
                        try:
                            args = _json.loads(tc.function.arguments)
                            result = str(fn(**args))
                        except Exception as e:
                            result = f"Error: {e}"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            return msg.content or ""

        return ARISE(agent_fn=agent_fn, reward_fn=reward_fn, config=config)

    def _summarize(self, agent: dict) -> dict:
        arise = agent.get("arise")
        stats = arise.stats if arise else {}
        return {
            "id": agent["id"],
            "name": agent["name"],
            "model": agent["model"],
            "status": agent.get("status", "stopped"),
            "skills_count": stats.get("active", 0),
            "success_rate": stats.get("recent_success_rate", 0.0),
            "episodes": stats.get("episodes_run", 0),
            "evolutions": len(arise.evolution_history) if arise else 0,
            "created_at": agent.get("created_at", ""),
        }

    def _detail(self, agent: dict) -> dict:
        summary = self._summarize(agent)
        arise = agent.get("arise")
        stats = arise.stats if arise else {}
        summary.update({
            "system_prompt": agent.get("system_prompt", ""),
            "tasks": agent.get("tasks", []),
            "reward_function": agent.get("reward_function", "task_success"),
            "allowed_imports": agent.get("allowed_imports"),
            "sandbox_backend": agent.get("sandbox_backend", "subprocess"),
            "failure_threshold": agent.get("failure_threshold", 5),
            "library_version": stats.get("library_version", 0),
            "avg_latency_ms": 0.0,
        })
        return summary
