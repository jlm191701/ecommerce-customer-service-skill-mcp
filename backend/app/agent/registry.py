from app.agent.contracts import Skill
from app.schemas.chat import ChatRequest, ConversationState


class SkillRegistry:
    def __init__(self, skills: list[Skill]) -> None:
        self._skills = sorted(skills, key=lambda skill: skill.priority, reverse=True)

    def select(self, request: ChatRequest, state: ConversationState) -> Skill | None:
        if not self._skills:
            return None

        ranked = [
            (skill.can_handle(request, state), skill.priority, skill)
            for skill in self._skills
        ]
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return ranked[0][2]
