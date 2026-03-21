from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from arise.skills.library import SkillLibrary
from arise.trajectory.store import TrajectoryStore


def run_tui(skills_path: str, trajectories_path: str) -> None:
    console = Console()
    lib = SkillLibrary(skills_path)
    store = TrajectoryStore(trajectories_path)

    stats = lib.stats()

    # Overall stats panel
    stats_text = (
        f"Library Version: {stats['library_version']}  |  "
        f"Active: {stats['active']}  |  "
        f"Testing: {stats['testing']}  |  "
        f"Deprecated: {stats['deprecated']}  |  "
        f"Total: {stats['total_skills']}  |  "
        f"Avg Success: {stats['avg_success_rate']:.1%}"
    )
    console.print(Panel(stats_text, title="ARISE Dashboard", border_style="blue"))

    # Skills table
    skills_table = Table(title="Skill Library")
    skills_table.add_column("Name", style="cyan")
    skills_table.add_column("Status", style="green")
    skills_table.add_column("Success Rate", justify="right")
    skills_table.add_column("Invocations", justify="right")
    skills_table.add_column("Origin")
    skills_table.add_column("ID", style="dim")

    all_rows = lib._conn.execute(
        "SELECT * FROM skills ORDER BY status, name"
    ).fetchall()
    for row in all_rows:
        skill = lib._row_to_skill(row)
        skills_table.add_row(
            skill.name,
            skill.status.value,
            f"{skill.success_rate:.1%}",
            str(skill.invocation_count),
            skill.origin.value,
            skill.id,
        )

    console.print(skills_table)

    # Evolution history
    history = lib.get_version_history()[:10]
    if history:
        history_table = Table(title="Recent Evolution History")
        history_table.add_column("Version", justify="right")
        history_table.add_column("Description")
        history_table.add_column("Skills", justify="right")
        history_table.add_column("Created At")

        for entry in history:
            history_table.add_row(
                str(entry["version"]),
                entry["description"] or "-",
                str(len(entry["active_skill_ids"])),
                entry["created_at"][:19] if entry["created_at"] else "-",
            )
        console.print(history_table)

    # Recent trajectories
    trajectories = store.get_recent(10)
    if trajectories:
        traj_table = Table(title="Recent Trajectories")
        traj_table.add_column("Task")
        traj_table.add_column("Reward", justify="right")
        traj_table.add_column("Steps", justify="right")
        traj_table.add_column("Time")

        for t in trajectories:
            task_short = t.task[:50] + ".." if len(t.task) > 50 else t.task
            traj_table.add_row(
                task_short,
                f"{t.reward:.2f}",
                str(len(t.steps)),
                t.timestamp.strftime("%Y-%m-%d %H:%M"),
            )
        console.print(traj_table)
