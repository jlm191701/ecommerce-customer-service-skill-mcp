from pathlib import Path
from typing import Any

import yaml

from app.agent.markdown_skill import MarkdownSkill, MarkdownSkillDefinition
from app.agent.contracts import Skill


class FileSkillLoader:
    def __init__(self, skills_path: Path) -> None:
        self._skills_path = skills_path

    def load(self) -> list[Skill]:
        if not self._skills_path.exists():
            return []

        skills: list[Skill] = []
        for skill_dir in sorted(self._skills_path.iterdir()):
            if not skill_dir.is_dir():
                continue
            manifest_path = skill_dir / "manifest.yaml"
            skill_path = skill_dir / "SKILL.md"
            if not manifest_path.exists() or not skill_path.exists():
                continue
            skills.append(self._load_markdown_skill(skill_dir, manifest_path, skill_path))
        return skills

    def _load_markdown_skill(
        self,
        skill_dir: Path,
        manifest_path: Path,
        skill_path: Path,
    ) -> MarkdownSkill:
        manifest = self._read_yaml(manifest_path)
        skill_body = skill_path.read_text(encoding="utf-8")
        references = self._read_references(skill_dir / "references")

        definition = MarkdownSkillDefinition(
            name=str(manifest["name"]),
            description=str(manifest.get("description", "")),
            priority=int(manifest.get("priority", 0)),
            capabilities=list(manifest.get("capabilities", [])),
            intents=list(manifest.get("intents", [])),
            skill_body=skill_body,
            references=references,
        )
        return MarkdownSkill(definition)

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Skill manifest must be a mapping: {path}")
        return loaded

    @staticmethod
    def _read_references(references_path: Path) -> dict[str, str]:
        if not references_path.exists():
            return {}
        references: dict[str, str] = {}
        for path in sorted(references_path.glob("*.md")):
            references[path.name] = path.read_text(encoding="utf-8")
        return references
