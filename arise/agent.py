from __future__ import annotations

import inspect
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from arise.config import ARISEConfig
from arise.skills.ab_test import SkillABTest
from arise.skills.forge import SkillForge
from arise.skills.library import SkillLibrary
from arise.skills.sandbox import Sandbox
from arise.skills.triggers import EvolutionTrigger
from arise.stores.base import SkillStore, TrajectoryReporter
from arise.stores.local import LocalSkillStore, LocalTrajectoryReporter
from arise.trajectory.logger import TrajectoryLogger
from arise.trajectory.store import TrajectoryStore
from arise.types import EvolutionReport, Skill, SkillOrigin, SkillStatus, Step, ToolSpec, Trajectory


class ARISE:
    """Self-evolving agent framework that synthesizes tools at runtime.

    ARISE wraps your agent function and automatically detects capability gaps
    from failure trajectories, synthesizes new Python tools via LLM, tests them
    in a sandbox, and promotes passing tools to the active library.

    Args:
        agent_fn: Your agent function with signature (task: str, tools: list) -> str.
        reward_fn: Evaluates trajectory quality, returns float in [0.0, 1.0].
        model: LLM model for tool synthesis (not your agent's model).
        sandbox: Custom sandbox for testing generated code.
        skill_library: Custom local skill library (local mode only).
        config: Full configuration object.
        agent: A Strands Agent instance (alternative to agent_fn).
        skill_store: Remote skill store for distributed mode (e.g., S3SkillStore).
        trajectory_reporter: Remote trajectory reporter for distributed mode (e.g., SQSTrajectoryReporter).
    """

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
            # Auto-detect LangGraph compiled graph (has get_graph method)
            elif hasattr(agent, "get_graph"):
                from arise.adapters.langgraph import langgraph_adapter

                agent_fn = langgraph_adapter(agent)
            else:
                raise TypeError(
                    f"Unsupported agent type: {type(agent).__name__}. "
                    "Pass a Strands Agent, a LangGraph compiled graph, "
                    "or use agent_fn= with a custom wrapper."
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
            registry = None
            if self.config.registry_bucket:
                from arise.registry import SkillRegistry
                registry = SkillRegistry(
                    bucket=self.config.registry_bucket,
                    prefix=self.config.registry_prefix,
                    region=self.config.aws_region,
                )
            llm_router = None
            if self.config.model_routes:
                from arise.llm_router import LLMRouter
                llm_router = LLMRouter(
                    routes=self.config.model_routes,
                    default=self.config.model,
                    auto_select=self.config.auto_select_model,
                )
            self.forge = SkillForge(
                model=self.config.model,
                sandbox=self.sandbox,
                max_retries=self.config.max_refinement_attempts,
                allowed_imports=self.config.allowed_imports,
                registry=registry,
                llm_router=llm_router,
            )
            self.trigger = EvolutionTrigger(self.config)

        self._episode_count = 0
        self._evolution_timestamps: list[float] = []
        self._last_evolution_episode = 0
        self._ab_tests: dict[str, SkillABTest] = {}
        self.evolution_history: list[EvolutionReport] = []

    def run(self, task: str, **kwargs: Any) -> str:
        """Run a single task through the agent with the current tool library.

        Returns the agent's response string. Trajectories are recorded and
        evolution is triggered automatically in local mode.
        """
        self._episode_count += 1
        tool_specs = self._skill_store.get_tool_specs()

        # Replace tool specs involved in A/B tests with selected variant
        ab_variants: dict[str, Skill] = {}  # skill_name -> selected Skill for this episode
        for name, ab in self._ab_tests.items():
            variant = ab.get_variant()
            ab_variants[name] = variant
            tool_specs = [
                variant.to_tool_spec() if ts.name == name else ts
                for ts in tool_specs
            ]

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
        if not isinstance(reward, (int, float)):
            raise TypeError(f"reward_fn must return a number, got {type(reward).__name__}")
        reward = float(reward)
        if reward != reward:  # NaN check
            raise ValueError("reward_fn returned NaN")
        trajectory.reward = max(0.0, min(1.0, reward))

        # Record A/B test outcomes and check for concluded tests
        for name, ab in list(self._ab_tests.items()):
            if name in ab_variants:
                ab.record(ab_variants[name], success=(trajectory.reward >= 0.5))
            if ab.status == "concluded" and self.skill_library is not None:
                winner = ab.winner
                loser = ab.loser
                if winner and loser:
                    self.skill_library.promote(winner.id)
                    self.skill_library.deprecate(loser.id, reason="Lost A/B test")
                    if self.config.verbose:
                        print(f"[ARISE] A/B test concluded: '{winner.name}' won over variant")
                del self._ab_tests[name]

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
        """Run multiple tasks in sequence, cycling through the task list.

        Args:
            tasks: List of task strings to train on.
            num_episodes: Total episodes to run (defaults to len(tasks)).
        """
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
        """Manually trigger an evolution cycle: detect gaps, synthesize tools, test and promote.

        Only works in local mode. In distributed mode, evolution is handled by ARISEWorker.
        """
        if self.forge is None or self.trajectory_store is None:
            return

        evolve_start = time.time()
        report = EvolutionReport()

        self._evolution_timestamps.append(evolve_start)
        self._last_evolution_episode = self._episode_count

        failures = self.trajectory_store.get_failures(n=self.config.failure_threshold * 2)
        if not failures:
            if self.config.verbose:
                print("[ARISE] No failures to analyze.")
            report.duration_ms = (time.time() - evolve_start) * 1000
            self.evolution_history.append(report)
            return

        gaps = self.forge.detect_gaps(failures, self._skill_store)
        report.gaps_detected = [g.suggested_name for g in gaps]
        if self.config.verbose:
            print(f"[ARISE] Found {len(gaps)} capability gaps.")

        # Build map of active skills by name for patch attempts
        active_skills_by_name = {s.name: s for s in self._skill_store.get_active_skills()}

        # Separate gaps: those with existing skills (patch candidates) vs new skills
        patch_gaps = [g for g in gaps if g.suggested_name in active_skills_by_name]
        new_gaps = [g for g in gaps if g.suggested_name not in active_skills_by_name]

        if not patch_gaps and not new_gaps:
            if self.config.verbose:
                print("[ARISE] All detected gaps already have active skills.")
            report.duration_ms = (time.time() - evolve_start) * 1000
            self.evolution_history.append(report)
            return

        # Try patching existing skills first
        for gap in patch_gaps:
            name = gap.suggested_name
            existing_skill = active_skills_by_name[name]
            relevant_failures = [
                t for t in failures
                if any(s.action == name or (s.error and name in (s.error or "")) for s in t.steps)
            ] or failures[:5]

            if self.config.verbose:
                print(f"[ARISE] Patching existing skill '{name}' instead of full synthesis...")

            try:
                patched = self.forge.patch(existing_skill, relevant_failures)
                result = self.sandbox.test_skill(patched)
                if result.success:
                    self.start_ab_test(existing_skill, patched)
                    report.tools_synthesized.append(name)
                    if self.config.verbose:
                        print(f"[ARISE] Patch for '{name}' passed sandbox — starting A/B test.")
                else:
                    report.tools_rejected.append({"name": name, "reason": "patch failed sandbox"})
                    if self.config.verbose:
                        print(f"[ARISE] Patch for '{name}' failed sandbox — skipping.")
            except Exception as e:
                report.tools_rejected.append({"name": name, "reason": str(e)})
                if self.config.verbose:
                    print(f"[ARISE] Failed to patch '{name}': {e}")

        # Filter new_gaps to those that fit within max_library_size
        active_count = len(self._skill_store.get_active_skills())
        remaining_capacity = self.config.max_library_size - active_count
        if remaining_capacity <= 0:
            if self.config.verbose:
                print("[ARISE] Library at max capacity. Skipping new gap synthesis.")
            new_gaps = []
        else:
            new_gaps = new_gaps[:remaining_capacity]

        if new_gaps:
            if self.config.verbose:
                print(f"[ARISE] Synthesizing {len(new_gaps)} tools in parallel (max_workers=3)...")

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self._synthesize_gap, gap, failures): gap
                    for gap in new_gaps
                }
                for future in as_completed(futures):
                    result = future.result()
                    if result is None:
                        gap = futures[future]
                        report.tools_rejected.append({"name": gap.suggested_name, "reason": "synthesis exception"})
                        continue
                    gap, skill, success = result
                    report.tools_synthesized.append(skill.name)
                    if success:
                        self.skill_library.add(skill)
                        self.skill_library.promote(skill.id)
                        report.tools_promoted.append(skill.name)
                        if self.config.verbose:
                            print(f"[ARISE] Skill '{skill.name}' created and promoted!")
                    else:
                        report.tools_rejected.append({"name": skill.name, "reason": "failed sandbox tests"})
                        self.skill_library.add(skill)
                        if self.config.verbose:
                            print(f"[ARISE] Skill '{skill.name}' added (testing).")

        report.duration_ms = (time.time() - evolve_start) * 1000
        self.evolution_history.append(report)

    def add_skill(self, fn: Callable, description: str = ""):
        """Manually add a Python function as a skill to the library.

        The function source is extracted via inspect and promoted immediately.
        """
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
        """Remove an active skill by name. Raises ValueError if not found."""
        if self.skill_library is None:
            raise RuntimeError("remove_skill() is not supported in distributed mode")
        for skill in self.skill_library.get_active_skills():
            if skill.name == name:
                self.skill_library.deprecate(skill.id, reason="Manually removed")
                return
        raise ValueError(f"No active skill named '{name}'")

    def start_ab_test(self, skill_a: Skill, skill_b: Skill, min_episodes: int = 20) -> SkillABTest:
        """Start an A/B test between two skill versions."""
        ab = SkillABTest(skill_a=skill_a, skill_b=skill_b, min_episodes=min_episodes)
        self._ab_tests[skill_a.name] = ab
        return ab

    @property
    def skills(self) -> list[Skill]:
        return self._skill_store.get_active_skills()

    @property
    def last_evolution(self) -> EvolutionReport | None:
        return self.evolution_history[-1] if self.evolution_history else None

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
        """Export all active skills as individual .py files to the given directory."""
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
        """Rollback the skill library to a previous version checkpoint."""
        if self.skill_library is None:
            raise RuntimeError("rollback() is not supported in distributed mode")
        self.skill_library.rollback(version)

    def _synthesize_gap(self, gap, failures):
        """Synthesize and validate a single gap. Returns (gap, skill, success) or None."""
        try:
            skill = self.forge.synthesize(gap, self._skill_store)
            result = self.sandbox.test_skill(skill)
            if result.success:
                adv_passed, adv_feedback = self.forge.adversarial_validate(skill)
                if not adv_passed:
                    if self.config.verbose:
                        print(f"[ARISE] Skill '{skill.name}' failed adversarial tests — refining...")
                    skill = self.forge.refine(skill, adv_feedback)
                    result = self.sandbox.test_skill(skill)
                    if not result.success:
                        if self.config.verbose:
                            print(f"[ARISE] Skill '{skill.name}' failed after refinement — keeping in testing.")
                        return (gap, skill, False)
                return (gap, skill, True)
            return (gap, skill, False)
        except Exception as e:
            if self.config.verbose:
                print(f"[ARISE] Failed: {gap.suggested_name}: {e}")
            return None

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
