from pathlib import Path

from app.infrastructure.skills.file_loader import FileSkillLoader


def test_file_skill_loader_loads_customer_service_core() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skills = FileSkillLoader(repo_root / "skills").load()

    assert [skill.name for skill in skills] == [
        "customer_service_core",
        "knowledge_base_authoring",
    ]
    assert skills[0].priority == 100
    assert "order_playbook.md" in skills[0]._definition.references
    assert skills[1].priority == 20
    assert "card-schema.md" in skills[1]._definition.references
