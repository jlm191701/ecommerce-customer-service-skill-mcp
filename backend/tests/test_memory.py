import asyncio
from pathlib import Path

from app.infrastructure.memory.event_entity_store import EventEntityMemoryStore
from app.infrastructure.memory.markdown_store import MarkdownLongTermMemoryStore


def test_markdown_memory_store_keeps_key_facts_only(tmp_path: Path) -> None:
    store = MarkdownLongTermMemoryStore(tmp_path)

    asyncio.run(
        store.update_from_turn(
            "user/with bad chars",
            "我叫小蒋，之后请用中文简洁回答。帮我查订单 64575145823542368",
            "您好，小蒋。订单正在派送中。",
        )
    )

    content = asyncio.run(store.load("user/with bad chars"))
    assert "用户称呼：小蒋" in content
    assert "偏好简洁直接的回答。" in content
    assert "偏好使用中文沟通。" in content
    assert "曾查询订单：64575145823542368" in content
    assert "您好，小蒋。订单正在派送中。" not in content


def test_markdown_memory_store_supports_chinese_user_id(tmp_path: Path) -> None:
    store = MarkdownLongTermMemoryStore(tmp_path)

    asyncio.run(store.update_from_turn("小蒋", "你好", "您好。"))

    assert (tmp_path / "users" / "小蒋.md").exists()


def test_event_entity_memory_store_materializes_key_entities(tmp_path: Path) -> None:
    store = EventEntityMemoryStore(tmp_path)

    asyncio.run(
        store.update_from_turn(
            "user/with bad chars",
            "我叫小蒋，之后请用中文简洁回答。帮我查订单 64575145823542368",
            "您好，小蒋。订单正在派送中。",
        )
    )

    content = asyncio.run(store.load("user/with bad chars"))
    assert "用户称呼：小蒋" in content
    assert "偏好简洁直接的回答。" in content
    assert "偏好使用中文沟通。" in content
    assert "曾查询订单：64575145823542368" in content
    assert "您好，小蒋。订单正在派送中。" not in content
    assert (tmp_path / "events" / "user_with_bad_chars.jsonl").exists()
    assert (tmp_path / "entities" / "user_with_bad_chars.json").exists()


def test_event_entity_memory_store_retrieves_by_query(tmp_path: Path) -> None:
    store = EventEntityMemoryStore(tmp_path, limit=2)

    asyncio.run(
        store.update_from_turn(
            "小蒋",
            "我的订单 64575145823542368 现在什么情况？",
            "系统提示权限不足，需要补充身份核验信息。",
        )
    )
    asyncio.run(
        store.update_from_turn(
            "小蒋",
            "Aurora Phone X1 支持多少瓦快充？",
            "支持最高 80W 有线快充。",
        )
    )

    order_memory = asyncio.run(store.retrieve("小蒋", "这个订单还需要核验吗？", limit=2))
    assert "曾查询订单：64575145823542368" in order_memory
    assert "身份核验" in order_memory
