import os
import shutil
import tempfile

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arise.types import Skill, SkillStatus, SkillOrigin
from arise.skills.library import SkillLibrary


def get_temp_lib():
    path = tempfile.mkdtemp()
    return SkillLibrary(path), path


def test_add_and_get():
    lib, path = get_temp_lib()
    try:
        skill = Skill(name="add", description="Add two numbers", implementation="def add(a, b): return a + b")
        lib.add(skill)
        retrieved = lib.get_skill(skill.id)
        assert retrieved is not None
        assert retrieved.name == "add"
        assert retrieved.status == SkillStatus.TESTING
    finally:
        shutil.rmtree(path)


def test_promote_and_active():
    lib, path = get_temp_lib()
    try:
        skill = Skill(name="mul", description="Multiply", implementation="def mul(a, b): return a * b")
        lib.add(skill)
        lib.promote(skill.id)
        active = lib.get_active_skills()
        assert len(active) == 1
        assert active[0].name == "mul"
        assert active[0].status == SkillStatus.ACTIVE
    finally:
        shutil.rmtree(path)


def test_deprecate():
    lib, path = get_temp_lib()
    try:
        skill = Skill(name="old", description="Old tool", implementation="def old(): pass")
        lib.add(skill)
        lib.promote(skill.id)
        lib.deprecate(skill.id, "no longer needed")
        active = lib.get_active_skills()
        assert len(active) == 0
        retrieved = lib.get_skill(skill.id)
        assert retrieved.status == SkillStatus.DEPRECATED
    finally:
        shutil.rmtree(path)


def test_get_tools():
    lib, path = get_temp_lib()
    try:
        skill = Skill(
            name="double",
            description="Double a number",
            implementation="def double(x):\n    return x * 2",
        )
        lib.add(skill)
        lib.promote(skill.id)
        tools = lib.get_tools()
        assert len(tools) == 1
        assert tools[0](5) == 10
    finally:
        shutil.rmtree(path)


def test_record_invocation():
    lib, path = get_temp_lib()
    try:
        skill = Skill(name="t", description="test", implementation="def t(): pass")
        lib.add(skill)
        lib.promote(skill.id)
        lib.record_invocation(skill.id, True, 100.0)
        lib.record_invocation(skill.id, False, 200.0, "some error")
        updated = lib.get_skill(skill.id)
        assert updated.invocation_count == 2
        assert updated.success_count == 1
        assert updated.success_rate == 0.5
        assert len(updated.error_log) == 1
    finally:
        shutil.rmtree(path)


def test_checkpoint_and_rollback():
    lib, path = get_temp_lib()
    try:
        s1 = Skill(name="a", description="a", implementation="def a(): pass")
        s2 = Skill(name="b", description="b", implementation="def b(): pass")
        lib.add(s1)
        lib.promote(s1.id)

        v1 = lib.checkpoint("v1 with just a")

        lib.add(s2)
        lib.promote(s2.id)
        assert len(lib.get_active_skills()) == 2

        lib.rollback(v1)
        active = lib.get_active_skills()
        assert len(active) == 1
        assert active[0].name == "a"
    finally:
        shutil.rmtree(path)


def test_search():
    lib, path = get_temp_lib()
    try:
        lib.add(Skill(name="detect_anomalies", description="Detect anomalies in time series data using z-score", implementation="def detect_anomalies(): pass", status=SkillStatus.ACTIVE))
        lib.promote(lib.get_active_skills()[-1].id) if lib.get_active_skills() else None
        # Force active
        lib._conn.execute("UPDATE skills SET status = 'active' WHERE name = 'detect_anomalies'")
        lib._conn.commit()

        lib.add(Skill(name="add", description="Add two numbers", implementation="def add(a,b): return a+b", status=SkillStatus.ACTIVE))
        lib._conn.execute("UPDATE skills SET status = 'active' WHERE name = 'add'")
        lib._conn.commit()

        results = lib.search("anomaly detection time series")
        assert len(results) > 0
        assert results[0].name == "detect_anomalies"
    finally:
        shutil.rmtree(path)


def test_stats():
    lib, path = get_temp_lib()
    try:
        s = Skill(name="x", description="x", implementation="def x(): pass")
        lib.add(s)
        lib.promote(s.id)
        stats = lib.stats()
        assert stats["active"] == 1
        assert stats["total_skills"] == 1
    finally:
        shutil.rmtree(path)


def test_version_history():
    lib, path = get_temp_lib()
    try:
        lib.checkpoint("initial")
        history = lib.get_version_history()
        assert len(history) >= 1
        assert history[0]["description"] == "initial"
    finally:
        shutil.rmtree(path)


def test_export_skill():
    lib, path = get_temp_lib()
    try:
        s = Skill(name="greet", description="Say hello", implementation="def greet(name):\n    return f'Hello {name}'")
        lib.add(s)
        exported = lib.export_skill(s.id)
        assert "def greet" in exported
        assert "ARISE Skill" in exported
    finally:
        shutil.rmtree(path)


if __name__ == "__main__":
    test_add_and_get()
    test_promote_and_active()
    test_deprecate()
    test_get_tools()
    test_record_invocation()
    test_checkpoint_and_rollback()
    test_search()
    test_stats()
    test_version_history()
    test_export_skill()
    print("All library tests passed!")
