from __future__ import annotations

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(prog="arise", description="ARISE — Self-Evolving Agent Framework")
    sub = parser.add_subparsers(dest="command")

    # status
    p_status = sub.add_parser("status", help="Show library statistics")
    p_status.add_argument("path", nargs="?", default="./arise_skills", help="Skill library path")

    # skills
    p_skills = sub.add_parser("skills", help="List active skills")
    p_skills.add_argument("path", nargs="?", default="./arise_skills", help="Skill library path")

    # inspect
    p_inspect = sub.add_parser("inspect", help="Inspect a skill")
    p_inspect.add_argument("path", help="Skill library path")
    p_inspect.add_argument("skill_id", help="Skill ID")

    # rollback
    p_rollback = sub.add_parser("rollback", help="Rollback to a version")
    p_rollback.add_argument("path", help="Skill library path")
    p_rollback.add_argument("version", type=int, help="Version number")

    # export
    p_export = sub.add_parser("export", help="Export skills as .py files")
    p_export.add_argument("path", help="Skill library path")
    p_export.add_argument("output", help="Output directory")

    # history
    p_history = sub.add_parser("history", help="Show trajectory history")
    p_history.add_argument("path", nargs="?", default="./arise_trajectories", help="Trajectory store path")
    p_history.add_argument("-n", type=int, default=10, help="Number of entries")

    # evolve (dry-run)
    p_evolve = sub.add_parser("evolve", help="Trigger or preview evolution")
    p_evolve.add_argument("--skills-path", default="./arise_skills", help="Skill library path")
    p_evolve.add_argument("--trajectories-path", default="./arise_trajectories", help="Trajectory store path")
    p_evolve.add_argument("--dry-run", action="store_true", help="Show what would be created without calling LLM")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "status":
        from arise.skills.library import SkillLibrary
        lib = SkillLibrary(args.path)
        stats = lib.stats()
        print(f"ARISE Skill Library — {args.path}")
        print(f"  Version:      {stats['library_version']}")
        print(f"  Active:       {stats['active']}")
        print(f"  Testing:      {stats['testing']}")
        print(f"  Deprecated:   {stats['deprecated']}")
        print(f"  Total:        {stats['total_skills']}")
        print(f"  Avg Success:  {stats['avg_success_rate']:.1%}")
        if stats["top_performers"]:
            print("\n  Top Performers:")
            for t in stats["top_performers"]:
                print(f"    {t['name']}: {t['success_rate']:.1%} ({t['invocations']} invocations)")

    elif args.command == "skills":
        from arise.skills.library import SkillLibrary
        lib = SkillLibrary(args.path)
        skills = lib.get_active_skills()
        if not skills:
            print("No active skills.")
            return
        print(f"{'Name':<25} {'Success':<10} {'Invocations':<12} {'Origin':<12} {'ID'}")
        print("-" * 75)
        for s in skills:
            print(f"{s.name:<25} {s.success_rate:<10.1%} {s.invocation_count:<12} {s.origin.value:<12} {s.id}")

    elif args.command == "inspect":
        from arise.skills.library import SkillLibrary
        lib = SkillLibrary(args.path)
        skill = lib.get_skill(args.skill_id)
        if skill is None:
            print(f"Skill {args.skill_id} not found.")
            sys.exit(1)
        print(f"Name:        {skill.name}")
        print(f"ID:          {skill.id}")
        print(f"Status:      {skill.status.value}")
        print(f"Origin:      {skill.origin.value}")
        print(f"Version:     {skill.version}")
        print(f"Success:     {skill.success_rate:.1%} ({skill.invocation_count} invocations)")
        print(f"Description: {skill.description}")
        print(f"\n--- Implementation ---\n{skill.implementation}")
        if skill.test_suite:
            print(f"\n--- Test Suite ---\n{skill.test_suite}")

    elif args.command == "rollback":
        from arise.skills.library import SkillLibrary
        lib = SkillLibrary(args.path)
        lib.rollback(args.version)
        print(f"Rolled back to version {args.version}.")

    elif args.command == "export":
        import os
        from arise.skills.library import SkillLibrary
        lib = SkillLibrary(args.path)
        os.makedirs(args.output, exist_ok=True)
        skills = lib.get_active_skills()
        for skill in skills:
            content = lib.export_skill(skill.id)
            filepath = os.path.join(args.output, f"{skill.name}.py")
            with open(filepath, "w") as f:
                f.write(content)
            print(f"Exported: {filepath}")
        print(f"\n{len(skills)} skills exported.")

    elif args.command == "evolve":
        from arise.skills.library import SkillLibrary
        from arise.skills.triggers import EvolutionTrigger
        from arise.trajectory.store import TrajectoryStore
        from arise.config import ARISEConfig

        lib = SkillLibrary(args.skills_path)
        store = TrajectoryStore(args.trajectories_path)
        config = ARISEConfig()
        trigger = EvolutionTrigger(config)

        recent = store.get_recent(config.plateau_window)
        should = trigger.should_evolve(recent, lib)
        print(f"Should evolve: {should}")

        failures = store.get_failures(n=config.failure_threshold * 2)
        print(f"Recent failures: {len(failures)}")

        if failures:
            patterns = trigger.get_failure_patterns(failures)
            if patterns:
                print("\nFailure patterns:")
                for p in patterns:
                    print(f"  [{p['count']}x] {p['error_pattern'][:80]}")
                    for task in p["example_tasks"][:2]:
                        print(f"       Task: {task[:60]}")

        if args.dry_run:
            print("\n[DRY RUN] Would analyze gaps and synthesize tools — no LLM calls made.")
        else:
            print("\nUse --dry-run to preview, or run evolve() from Python to execute.")

    elif args.command == "history":
        from arise.trajectory.store import TrajectoryStore
        store = TrajectoryStore(args.path)
        trajectories = store.get_recent(args.n)
        if not trajectories:
            print("No trajectories recorded.")
            return
        print(f"{'Task':<50} {'Reward':<8} {'Steps':<7} {'Time'}")
        print("-" * 85)
        for t in trajectories:
            task_short = t.task[:48] + ".." if len(t.task) > 48 else t.task
            print(f"{task_short:<50} {t.reward:<8.2f} {len(t.steps):<7} {t.timestamp.strftime('%Y-%m-%d %H:%M')}")


if __name__ == "__main__":
    main()
