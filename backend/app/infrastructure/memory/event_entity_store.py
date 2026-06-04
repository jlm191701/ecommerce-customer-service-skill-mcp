from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


@dataclass
class MemoryEvent:
    event_id: str
    user_id: str
    event_type: str
    topic: str
    content: str
    attrs: dict[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    business_weight: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "topic": self.topic,
            "content": self.content,
            "attrs": self.attrs,
            "occurred_at": self.occurred_at,
            "business_weight": self.business_weight,
        }


@dataclass
class MemoryEntity:
    entity_type: str
    key: str
    summary: str
    attrs: dict[str, Any] = field(default_factory=dict)
    event_count: int = 0
    active_count: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "key": self.key,
            "summary": self.summary,
            "attrs": self.attrs,
            "event_count": self.event_count,
            "active_count": self.active_count,
            "updated_at": self.updated_at,
        }


class EventEntityMemoryStore:
    """VikingMem-lite event/entity long-term memory store.

    It keeps selected events from conversation turns and materializes compact
    entities such as user profile, service preference, customer issue, and
    purchase interest. Retrieval uses lexical recall plus recency/business
    weights, which mirrors the lightweight version of VikingMem's multi-path
    memory recall without requiring a vector database.
    """

    INDEX_VERSION = 1

    def __init__(self, memory_path: Path, limit: int = 6) -> None:
        self._memory_path = memory_path
        self._events_path = memory_path / "events"
        self._entities_path = memory_path / "entities"
        self._limit = limit
        self._events_path.mkdir(parents=True, exist_ok=True)
        self._entities_path.mkdir(parents=True, exist_ok=True)

    async def load(self, user_id: str) -> str:
        return await self.retrieve(user_id, "")

    async def retrieve(self, user_id: str, query: str, limit: int | None = None) -> str:
        entities = self._load_entities(user_id)
        if not entities:
            return ""

        query_tokens = self._tokens(query)
        ranked = sorted(
            entities,
            key=lambda entity: self._entity_score(entity, query_tokens),
            reverse=True,
        )[: limit or self._limit]

        for entity in ranked:
            entity.active_count += 1
        self._write_entities(user_id, entities)

        return self._render(user_id, ranked, query=query)

    async def update_from_turn(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> None:
        events = self._extract_events(user_id, user_message, assistant_message)
        if not events:
            return

        self._append_events(user_id, events)
        entities = self._load_entities(user_id)
        by_key = {self._entity_key(entity): entity for entity in entities}

        for event in events:
            entity = self._entity_from_event(event)
            key = self._entity_key(entity)
            current = by_key.get(key)
            if current:
                self._merge_entity(current, entity)
            else:
                by_key[key] = entity

        self._write_entities(user_id, list(by_key.values()))

    def _extract_events(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> list[MemoryEvent]:
        now = datetime.now(timezone.utc).isoformat()
        clean_user = self._single_line(user_message)
        clean_assistant = self._single_line(assistant_message)
        events: list[MemoryEvent] = []

        def add(
            event_type: str,
            topic: str,
            content: str,
            attrs: dict[str, Any] | None = None,
            weight: float = 0.5,
        ) -> None:
            events.append(
                MemoryEvent(
                    event_id=f"evt_{uuid4().hex}",
                    user_id=user_id,
                    event_type=event_type,
                    topic=topic,
                    content=content,
                    attrs=attrs or {},
                    occurred_at=now,
                    business_weight=weight,
                )
            )

        add("profile", "identity", f"用户 ID：{user_id}", {"user_id": user_id}, 0.7)

        name = self._extract_name(clean_user)
        if name:
            add("profile", "identity", f"用户称呼：{name}", {"display_name": name}, 0.8)

        if "中文" in clean_user or re.search(r"[\u4e00-\u9fff]", clean_user):
            add("preference", "language", "偏好使用中文沟通。", {"language": "zh-CN"}, 0.6)

        if any(word in clean_user for word in ["简洁", "直接", "短一点", "不用太长"]):
            add("preference", "style", "偏好简洁直接的回答。", {"style": "concise"}, 0.7)

        for order_id in self._extract_order_ids(clean_user):
            add(
                "customer_issue",
                "order",
                f"曾查询订单：{order_id}",
                {"order_id": order_id},
                0.9,
            )

        if any(word in clean_user for word in ["人工", "转人工", "真人客服"]):
            add(
                "customer_issue",
                "handoff",
                "曾表达过人工客服需求。",
                {"handoff_requested": True},
                0.8,
            )

        if any(word in clean_user for word in ["价保", "保价", "降价", "差价"]):
            add(
                "purchase_interest",
                "price_protection",
                "关注数码产品价保或差价处理。",
                {"interest": "price_protection"},
                0.75,
            )

        if any(word in clean_user for word in ["快充", "参数", "配置", "多少钱", "价格"]):
            add(
                "purchase_interest",
                "product_specs",
                "关注商品参数、配置或价格信息。",
                {"interest": "product_specs"},
                0.65,
            )

        if any(word in clean_assistant for word in ["无法查询", "需要订单号", "核验", "权限不足"]):
            add(
                "customer_issue",
                "verification",
                "部分查询任务可能需要用户补充订单号或身份核验信息。",
                {"needs_verification": True},
                0.85,
            )

        return self._dedupe_events(events)

    def _entity_from_event(self, event: MemoryEvent) -> MemoryEntity:
        entity_type_by_event = {
            "profile": "user_profile",
            "preference": "service_preference",
            "customer_issue": "customer_issue",
            "purchase_interest": "purchase_preference",
        }
        return MemoryEntity(
            entity_type=entity_type_by_event.get(event.event_type, event.event_type),
            key=event.topic,
            summary=event.content,
            attrs=dict(event.attrs),
            event_count=1,
            active_count=0,
            updated_at=event.occurred_at,
        )

    def _merge_entity(self, current: MemoryEntity, incoming: MemoryEntity) -> None:
        current.event_count += incoming.event_count
        current.updated_at = incoming.updated_at
        current.attrs = {**current.attrs, **incoming.attrs}

        summaries = self._split_summary(current.summary)
        if incoming.summary not in summaries:
            summaries.append(incoming.summary)
        current.summary = "；".join(summaries[-5:])

    def _entity_score(self, entity: MemoryEntity, query_tokens: set[str]) -> float:
        text = f"{entity.entity_type} {entity.key} {entity.summary} {json.dumps(entity.attrs, ensure_ascii=False)}"
        entity_tokens = self._tokens(text)
        overlap = len(query_tokens & entity_tokens) / max(len(query_tokens), 1) if query_tokens else 0.0
        lexical_score = overlap if query_tokens else 0.5
        recency_score = self._recency_score(entity.updated_at)
        hotness_score = self._hotness_score(entity.active_count, entity.updated_at)
        business_score = self._business_score(entity)
        return 0.55 * lexical_score + 0.2 * recency_score + 0.15 * business_score + 0.1 * hotness_score

    @staticmethod
    def _business_score(entity: MemoryEntity) -> float:
        if entity.entity_type in {"customer_issue", "user_profile"}:
            return 1.0
        if entity.entity_type in {"service_preference", "purchase_preference"}:
            return 0.7
        return 0.5

    @staticmethod
    def _recency_score(updated_at: str) -> float:
        try:
            updated = datetime.fromisoformat(updated_at)
        except ValueError:
            return 0.0
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - updated).total_seconds() / 86400.0, 0.0)
        return math.exp(-(math.log(2) / 7.0) * age_days)

    def _hotness_score(self, active_count: int, updated_at: str) -> float:
        freq = 1.0 / (1.0 + math.exp(-math.log1p(active_count)))
        return freq * self._recency_score(updated_at)

    def _render(self, user_id: str, entities: list[MemoryEntity], *, query: str) -> str:
        parts = [
            f"# 用户长期记忆: {user_id}",
            "",
            "这份记忆来自 Event-Entity Memory Store，只保留稳定或高价值信息。",
        ]
        if query:
            parts.extend(["", f"检索问题：{query}"])
        groups: dict[str, list[MemoryEntity]] = {}
        for entity in entities:
            groups.setdefault(entity.entity_type, []).append(entity)

        labels = {
            "user_profile": "用户画像",
            "service_preference": "服务偏好",
            "customer_issue": "客户问题",
            "purchase_preference": "购买/咨询偏好",
        }
        for entity_type in ["user_profile", "service_preference", "customer_issue", "purchase_preference"]:
            items = groups.get(entity_type, [])
            if not items:
                continue
            parts.extend(["", f"## {labels.get(entity_type, entity_type)}"])
            for entity in items:
                parts.append(f"- [{entity.key}] {entity.summary}")
        return "\n".join(parts)

    def _load_entities(self, user_id: str) -> list[MemoryEntity]:
        path = self._entities_file(user_id)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if payload.get("version") != self.INDEX_VERSION:
            return []
        return [
            MemoryEntity(
                entity_type=item["entity_type"],
                key=item["key"],
                summary=item["summary"],
                attrs=item.get("attrs", {}),
                event_count=int(item.get("event_count", 0)),
                active_count=int(item.get("active_count", 0)),
                updated_at=item.get("updated_at") or datetime.now(timezone.utc).isoformat(),
            )
            for item in payload.get("entities", [])
        ]

    def _write_entities(self, user_id: str, entities: list[MemoryEntity]) -> None:
        payload = {
            "version": self.INDEX_VERSION,
            "user_id": user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entities": [entity.to_dict() for entity in sorted(entities, key=self._entity_key)],
        }
        self._entities_file(user_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _append_events(self, user_id: str, events: list[MemoryEvent]) -> None:
        path = self._events_file(user_id)
        with path.open("a", encoding="utf-8") as file:
            for event in events:
                file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def _events_file(self, user_id: str) -> Path:
        return self._events_path / f"{self._safe_user_id(user_id)}.jsonl"

    def _entities_file(self, user_id: str) -> Path:
        return self._entities_path / f"{self._safe_user_id(user_id)}.json"

    @staticmethod
    def _entity_key(entity: MemoryEntity) -> str:
        return f"{entity.entity_type}:{entity.key}"

    @staticmethod
    def _safe_user_id(user_id: str) -> str:
        safe_user_id = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", user_id).strip("._")
        return safe_user_id or "anonymous"

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

    @staticmethod
    def _tokens(text: str) -> set[str]:
        lowered = text.lower()
        tokens = set(re.findall(r"[a-z0-9_]+", lowered))
        tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", lowered))
        for word in ["订单", "人工", "价保", "快充", "参数", "中文", "核验", "权限"]:
            if word in lowered:
                tokens.add(word)
        return tokens

    @staticmethod
    def _single_line(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _split_summary(summary: str) -> list[str]:
        return [item.strip() for item in summary.split("；") if item.strip()]

    @staticmethod
    def _dedupe_events(events: list[MemoryEvent]) -> list[MemoryEvent]:
        seen: set[tuple[str, str, str]] = set()
        deduped = []
        for event in events:
            key = (event.event_type, event.topic, event.content)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)
        return deduped
