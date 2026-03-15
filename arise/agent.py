from __future__ import annotations

import inspect
import sys
import time
from typing import Any, Callable

from arise.config import ARISEConfig
from arise.skills.forge import SkillForge
from arise.skills.library import SkillLibrary
from arise.skills.sandbox import Sandbox
from arise.skills.triggers import EvolutionTrigger
from arise.stores.base import SkillStore, TrajectoryReporter
from arise.stores.local import LocalSkillStore, LocalTrajectoryReporter
from arise.trajectory.logger import TrajectoryLogger
from arise.trajectory.store import TrajectoryStore
from arise.types import Skill, SkillOrigin, SkillStatus, Step, ToolSpec, Trajectory


class ARISE:
    def __init__(
        self,
        agent_fn: Callable[[str, list[Callable]], str] | None = None,
        reward_fn: Callable[[Trajectory], float] = ...,  # type: ignore[assignment]
        model: str = "gpt-4o-mini",
        sandbox: Sandbox | None = None,
        skill_library: SkillLibrary | None = None,
        config: ARISEConfig | None = None,
        agent: Any | None = None,
        skill_store: SkillStore | None = None,
        trajectory_reporter: TrajectoryReporter | None = None,
    ):
        if agent is not None and agent_fn is not None:
            raise ValueError("Provide either 'agent' or 'agent_fn', not both.")

        if agent is not None:
            # Auto-detect Strands Agent (has tool_registry attribute)
            if hasattr(agent, "tool_registry"):
                from arise.adapters.strands import strands_adapter

                agent_fn = strands_adapter(agent)
            else:
                raise TypeError(
                    f"Unsupported agent type: {type(agent).__name__}. "
                    "Pass a Strands Agent or use agent_fn= with a custom wrapper."
                )

        if agent_fn is None:
            raise ValueError("Either 'agent' or 'agent_fn' must be provided.")

        self.agent_fn = agent_fn
        self.reward_fn = reward_fn
        self.config = config or ARISEConfig(model=model)
        self.config.model = model

        self.sandbox = sandbox or Sandbox(
            backend=self.config.sandbox_backend,
            timeout=self.config.sandbox_timeout,
        )

        # Distributed mode: use provided stores, skip local evolution
        if skill_store is not None:
            self._skill_store = skill_store
            self._trajectory_reporter = trajectory_reporter
            # No local library/trajectory store needed
            self.skill_library = None
            self.trajectory_store = None
            self.forge = None
            self.trigger = None
        else:
            # Local mode: backward compatible
            self.skill_library = skill_library or SkillLibrary(self.config.skill_store_path)
            self.trajectory_store = TrajectoryStore(self.config.trajectory_store_path)
            self._skill_store = LocalSkillStore(self.skill_library)
            self._trajectory_reporter = LocalTrajectoryReporter(self.trajectory_store)
            self.forge = SkillForge(
                model=self.config.model,
                sandbox=self.sandbox,
                max_retries=self.config.max_refinement_attempts,
            )
            self.trigger = EvolutionTrigger(self.config)

        self._episode_count = 0
        self._evolution_timestamps: list[float] = []
        self._last_evolution_episode = 0

    def run(self, task: str, **kwargs: Any) -> str:
        self._episode_count += 1
        tool_specs = self._skill_store.get_tool_specs()

        # Build trajectory in-memory
        trajectory = Trajectory(
            task=task,
            skill_library_version=self._skill_store.get_version(),
        )

        # Wrap tool specs to record invocations
        wrapped_tools = [self._wrap_tool_spec(ts, trajectory) for ts in tool_specs]

        start = time.time()
        try:
            result = self.agent_fn(task, wrapped_tools)
            elapsed = (time.time() - start) * 1000

            trajectory.steps.append(Step(
                observation="Agent returned result",
                reasoning="",
                action="respond",
                result=str(result)[:500],
                latency_ms=elapsed,
            ))
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            result = f"Error: {e}"
            trajectory.steps.append(Step(
                observation="Agent raised exception",
                reasoning="",
                action="error",
                error=str(e),
                latency_ms=elapsed,
            ))

        # Compute reward
        trajectory.outcome = str(result)[:1000]
        trajectory.metadata.update(kwargs)
        reward = self.reward_fn(trajectory)
        trajectory.reward = reward

        # Report trajectory (fire-and-forget)
        if self._trajectory_reporter is not None:
            self._trajectory_reporter.report(trajectory)

        if self.config.verbose:
            status = "OK" if reward >= 0.5 else "FAIL"
            print(f"[ARISE] Episode {self._episode_count} | {status} | reward={reward:.2f} | skills={len(tool_specs)}")

        # Local mode: prune trajectories and check evolution triggers
        if self.trajectory_store is not None:
            self._maybe_prune_trajectories()

        if self.trigger is not None and self.trajectory_store is not None:
            episodes_since_evolution = self._episode_count - self._last_evolution_episode
            recent = self.trajectory_store.get_recent(max(episodes_since_evolution, self.config.plateau_window))
            recent = recent[:episodes_since_evolution] if episodes_since_evolution > 0 else recent
            if self.trigger.should_evolve(recent, self._skill_store):
                if not self._can_evolve():
                    if self.config.verbose:
                        print("[ARISE] Evolution rate limit reached — skipping")
                else:
                    if self.config.verbose:
                        print("[ARISE] Evolution triggered — analyzing gaps...")
                    self.evolve()

        return result

    def train(self, tasks: list[str], num_episodes: int | None = None):
        total = num_episodes or len(tasks)
        for i in range(total):
            task = tasks[i % len(tasks)]
            if self.config.verbose:
                print(f"\n[ARISE] Training episode {i + 1}/{total}: {task[:80]}...")
            self.run(task)

        if self.config.verbose:
            if self.trajectory_store is not None:
                rate = self.trajectory_store.success_rate(total)
                print(f"\n[ARISE] Training complete. Success rate: {rate:.1%}")
            print(f"[ARISE] Active skills: {len(self._skill_store.get_active_skills())}")

    def evolve(self):
        if self.forge is None or self.trajectory_store is None:
            return

        self._evolution_timestamps.append(time.time())
        self._last_evolution_episode = self._episode_count

        failures = self.trajectory_store.get_failures(n=self.config.failure_threshold * 2)
        if not failures:
            if self.config.verbose:
                print("[ARISE] No failures to analyze.")
            return

        gaps = self.forge.detect_gaps(failures, self._skill_store)
        if self.config.verbose:
            print(f"[ARISE] Found {len(gaps)} capability gaps.")

        # Skip gaps where a skill with that name already exists
        active_names = {s.name for s in self._skill_store.get_active_skills()}
        gaps = [g for g in gaps if g.suggested_name not in active_names]
        if not gaps:
            if self.config.verbose:
                print("[ARISE] All detected gaps already have active skills.")
            return

        for gap in gaps:
            if self.config.verbose:
                print(f"[ARISE] Synthesizing tool: {gap.suggested_name}...")

            active_count = len(self._skill_store.get_active_skills())
            if active_count >= self.config.max_library_size:
                if self.config.verbose:
                    print("[ARISE] Library at max capacity. Skipping.")
                break

            try:
                skill = self.forge.synthesize(gap, self._skill_store)
                result = self.sandbox.test_skill(skill)

                if result.success:
                    # Adversarial validation before promotion
                    adv_passed, adv_feedback = self.forge.adversarial_validate(skill)
                    if not adv_passed:
                        if self.config.verbose:
                            print(f"[ARISE] Skill '{skill.name}' failed adversarial tests — refining...")
                        skill = self.forge.refine(skill, adv_feedback)
                        result = self.sandbox.test_skill(skill)
                        if not result.success:
                            if self.config.verbose:
                                print(f"[ARISE] Skill '{skill.name}' failed after refinement — keeping in testing.")
                            self.skill_library.add(skill)
                            continue

                    self.skill_library.add(skill)
                    self.skill_library.promote(skill.id)
                    if self.config.verbose:
                        print(f"[ARISE] Skill '{skill.name}' created and promoted!")
                else:
                    self.skill_library.add(skill)
                    if self.config.verbose:
                        failed = [t.test_name for t in result.test_results if not t.passed]
                        print(f"[ARISE] Skill '{skill.name}' added (testing) — {len(failed)} tests failing.")
            except Exception as e:
                if self.config.verbose:
                    print(f"[ARISE] Failed to synthesize '{gap.suggested_name}': {e}")

        # Composition is disabled in v0.1 — it tends to create low-quality tools
        # TODO: re-enable with better heuristics in v0.2

    def add_skill(self, fn: Callable, description: str = ""):
        if self.skill_library is None:
            raise RuntimeError("add_skill() is not supported in distributed mode")
        source = inspect.getsource(fn)
        skill = Skill(
            name=fn.__name__,
            description=description or fn.__doc__ or "",
            implementation=source,
            origin=SkillOrigin.MANUAL,
            status=SkillStatus.ACTIVE,
        )
        self.skill_library.add(skill)
        self.skill_library.promote(skill.id)

    def remove_skill(self, name: str):
        if self.skill_library is None:
            raise RuntimeError("remove_skill() is not supported in distributed mode")
        for skill in self.skill_library.get_active_skills():
            if skill.name == name:
                self.skill_library.deprecate(skill.id, reason="Manually removed")
                return
        raise ValueError(f"No active skill named '{name}'")

    @property
    def skills(self) -> list[Skill]:
        return self._skill_store.get_active_skills()

    @property
    def stats(self) -> dict:
        stats: dict[str, Any] = {
            "episodes_run": self._episode_count,
            "active": len(self._skill_store.get_active_skills()),
            "library_version": self._skill_store.get_version(),
        }
        if self.skill_library is not None:
            lib_stats = self.skill_library.stats()
            lib_stats["episodes_run"] = self._episode_count
            if self.trajectory_store is not None:
                lib_stats["recent_success_rate"] = round(
                    self.trajectory_store.success_rate(50), 3
                )
            return lib_stats
        if self.trajectory_store is not None:
            stats["recent_success_rate"] = round(
                self.trajectory_store.success_rate(50), 3
            )
        return stats

    def export(self, path: str):
        if self.skill_library is None:
            raise RuntimeError("export() is not supported in distributed mode")
        import os
        os.makedirs(path, exist_ok=True)
        for skill in self.skill_library.get_active_skills():
            content = self.skill_library.export_skill(skill.id)
            filepath = os.path.join(path, f"{skill.name}.py")
            with open(filepath, "w") as f:
                f.write(content)

    def rollback(self, version: int):
        if self.skill_library is None:
            raise RuntimeError("rollback() is not supported in distributed mode")
        self.skill_library.rollback(version)

    def _wrap_tool_spec(self, tool_spec: ToolSpec, trajectory: Trajectory) -> ToolSpec:
        skill_id = tool_spec.skill_id
        original_fn = tool_spec.fn

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = original_fn(*args, **kwargs)
                elapsed = (time.time() - start) * 1000
                trajectory.steps.append(Step(
                    observation=f"Called {tool_spec.name}",
                    reasoning="",
                    action=tool_spec.name,
                    action_input={"args": str(args)[:200], "kwargs": str(kwargs)[:200]},
                    result=str(result)[:500],
                    latency_ms=elapsed,
                ))
                if skill_id:
                    self._skill_store.record_invocation(skill_id, True, elapsed)
                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                trajectory.steps.append(Step(
                    observation=f"Called {tool_spec.name}",
                    reasoning="",
                    action=tool_spec.name,
                    action_input={"args": str(args)[:200], "kwargs": str(kwargs)[:200]},
                    error=str(e),
                    latency_ms=elapsed,
                ))
                if skill_id:
                    self._skill_store.record_invocation(skill_id, False, elapsed, str(e))
                raise

        wrapped.__name__ = tool_spec.name
        wrapped.__doc__ = tool_spec.description

        return ToolSpec(
            name=tool_spec.name,
            description=tool_spec.description,
            parameters=tool_spec.parameters,
            fn=wrapped,
            skill_id=skill_id,
        )

    def _can_evolve(self) -> bool:
        now = time.time()
        one_hour_ago = now - 3600
        self._evolution_timestamps = [t for t in self._evolution_timestamps if t > one_hour_ago]
        return len(self._evolution_timestamps) < self.config.max_evolutions_per_hour

    def _maybe_prune_trajectories(self):
        if self.trajectory_store is None:
            return
        max_t = self.config.max_trajectories
        count_row = self.trajectory_store._conn.execute(
            "SELECT COUNT(*) as c FROM trajectories"
        ).fetchone()
        if count_row and count_row["c"] > max_t:
            excess = count_row["c"] - max_t
            self.trajectory_store._conn.execute(
                "DELETE FROM trajectories WHERE id IN (SELECT id FROM trajectories ORDER BY timestamp ASC LIMIT ?)",
                (excess,),
            )
            self.trajectory_store._conn.commit()
