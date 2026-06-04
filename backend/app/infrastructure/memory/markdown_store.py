from pathlib import Path
import re


class MarkdownLongTermMemoryStore:
    def __init__(self, memory_path: Path) -> None:
        self._users_path = memory_path / "users"
        self._users_path.mkdir(parents=True, exist_ok=True)

    async def load(self, user_id: str) -> str:
        path = self._path_for(user_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def update_from_turn(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        path = self._path_for(user_id)
        memory = self._parse(path.read_text(encoding="utf-8") if path.exists() else "")
        self._extract_facts(memory, user_id, user_message, assistant_message)
        path.write_text(self._render(user_id, memory), encoding="utf-8")

    def _extract_facts(
        self,
        memory: dict[str, set[str]],
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        clean_user_message = self._single_line(user_message)
        clean_assistant_message = self._single_line(assistant_message)

        memory["用户资料"].add(f"用户 ID：{user_id}")

        name = self._extract_name(clean_user_message)
        if name:
            memory["用户资料"].add(f"用户称呼：{name}")

        for order_id in self._extract_order_ids(clean_user_message):
            memory["历史重要事项"].add(f"曾查询订单：{order_id}")

        if any(word in clean_user_message for word in ["简洁", "直接", "短一点", "不用太长"]):
            memory["服务偏好"].add("偏好简洁直接的回答。")

        if "中文" in clean_user_message or re.search(r"[\u4e00-\u9fff]", clean_user_message):
            memory["服务偏好"].add("偏好使用中文沟通。")

        if any(word in clean_user_message for word in ["人工", "转人工", "真人客服"]):
            memory["历史重要事项"].add("曾表达过人工客服需求。")

        if any(word in clean_assistant_message for word in ["无法查询", "需要订单号", "提供订单号"]):
            memory["待确认"].add("部分查询任务可能需要用户补充订单号或身份信息。")

    @staticmethod
    def _parse(content: str) -> dict[str, set[str]]:
        sections = {
            "用户资料": set(),
            "服务偏好": set(),
            "历史重要事项": set(),
            "待确认": set(),
        }
        current_section: str | None = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                name = stripped.removeprefix("## ").strip()
                current_section = name if name in sections else None
                continue
            if current_section and stripped.startswith("- "):
                sections[current_section].add(stripped.removeprefix("- ").strip())
        return sections

    @staticmethod
    def _render(user_id: str, memory: dict[str, set[str]]) -> str:
        parts = [
            f"# 用户长期记忆: {user_id}",
            "",
            "这份文件只保存稳定或重要的用户信息，不保存完整聊天记录。",
            "",
        ]
        for section in ["用户资料", "服务偏好", "历史重要事项", "待确认"]:
            parts.append(f"## {section}")
            items = sorted(memory.get(section, set()))
            if items:
                parts.extend(f"- {item}" for item in items)
            else:
                parts.append("- 暂无")
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _extract_name(message: str) -> str | None:
        patterns = [
            r"我叫([\u4e00-\u9fffA-Za-z0-9_-]{1,20})",
            r"我是([\u4e00-\u9fffA-Za-z0-9_-]{1,20})",
            r"叫我([\u4e00-\u9fffA-Za-z0-9_-]{1,20})",
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                name = match.group(1).strip()
                if name not in {"智能客服", "客服", "用户"}:
                    return name
        return None

    @staticmethod
    def _extract_order_ids(message: str) -> list[str]:
        return re.findall(r"\b\d{8,32}\b", message)

    def _path_for(self, user_id: str) -> Path:
        safe_user_id = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", user_id).strip("._")
        if not safe_user_id:
            safe_user_id = "anonymous"
        return self._users_path / f"{safe_user_id}.md"

    @staticmethod
    def _single_line(value: str) -> str:
        return " ".join(value.split())
