from pathlib import Path
import asyncio
import json

from app.infrastructure.knowledge.local_search import LocalKnowledgeSearch
from app.infrastructure.mcp.mock_gateway import MockMCPGateway


def test_local_knowledge_search_finds_markdown_card(tmp_path: Path) -> None:
    card = tmp_path / "after_sales" / "returns.md"
    card.parent.mkdir()
    card.write_text(
        """---
title: 退换货政策
category: after_sales
keywords:
  - 退货
  - 退款
updated_at: 2026-06-03
---

商品签收后符合售后条件时，可以申请退货或退款。
""",
        encoding="utf-8",
    )

    result = LocalKnowledgeSearch(tmp_path).search("退货规则是什么？")

    assert result["status"] == "success"
    assert result["data"]["results"][0]["title"] == "退换货政策"
    assert result["data"]["results"][0]["source"] == "after_sales/returns.md"
    assert result["data"]["index"]["method"] == "openviking_lite_query_plan_hierarchical_rerank"
    assert result["data"]["query_plan"][0]["intent"] == "after_sales_policy"


def test_local_knowledge_search_builds_hierarchical_index(tmp_path: Path) -> None:
    card = tmp_path / "product" / "phone.md"
    card.parent.mkdir()
    card.write_text(
        """---
title: Aurora Phone X1 参数
category: product_phone
keywords:
  - Aurora Phone X1
  - 手机
  - 快充
---

Aurora Phone X1 支持 80W 有线快充和 30W 无线充电。
""",
        encoding="utf-8",
    )

    search = LocalKnowledgeSearch(tmp_path)
    result = search.search("Aurora Phone X1 快充")

    index_path = tmp_path / ".index" / "knowledge_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    levels = {record["level"] for record in index["records"].values()}

    assert result["status"] == "success"
    assert index_path.exists()
    assert index["version"] == LocalKnowledgeSearch.INDEX_VERSION
    assert levels == {0, 1, 2}
    assert "aurora" in index["inverted"]
    assert result["data"]["index"]["records"] == len(index["records"])


def test_local_knowledge_search_returns_not_found_for_unmatched_query(tmp_path: Path) -> None:
    card = tmp_path / "billing.md"
    card.write_text(
        """---
title: 发票规则
category: billing
keywords:
  - 发票
---

订单完成后可以申请开具发票。
""",
        encoding="utf-8",
    )

    result = LocalKnowledgeSearch(tmp_path).search("会员等级怎么升级？")

    assert result["status"] == "failed"
    assert result["error_code"] == "not_found"
    assert result["data"]["results"] == []


def test_local_knowledge_search_returns_evidence_and_relations(tmp_path: Path) -> None:
    product = tmp_path / "product" / "aurora_phone_x1.md"
    price = tmp_path / "product" / "aurora_phone_x1_price.md"
    product.parent.mkdir()
    product.write_text(
        """---
title: Aurora Phone X1 参数
category: product
keywords:
  - Aurora Phone X1
  - 快充
  - 80W
product_ids:
  - aurora phone x1
---

Aurora Phone X1 支持最高 80W 有线快充，并支持 30W 无线充电。
""",
        encoding="utf-8",
    )
    price.write_text(
        """---
title: Aurora Phone X1 价格
category: product
keywords:
  - Aurora Phone X1
  - 价格
product_ids:
  - aurora phone x1
---

Aurora Phone X1 12GB+256GB 版本建议零售价为 3999 元。
""",
        encoding="utf-8",
    )

    result = LocalKnowledgeSearch(tmp_path).search("Aurora Phone X1 支持多少瓦快充？")
    first = result["data"]["results"][0]

    assert result["status"] == "success"
    assert first["title"] == "Aurora Phone X1 参数"
    assert first["evidence"]
    assert first["relations"][0]["relation"] == "same_product"


def test_local_knowledge_search_uses_query_plan_for_policy_resource(tmp_path: Path) -> None:
    policy = tmp_path / "policy" / "price.md"
    policy.parent.mkdir()
    policy.write_text(
        """---
title: 数码产品价保政策
category: policy
keywords:
  - 价保
  - 保价
  - 差价
---

数码商品支持订单签收后 7 天内价保。同一商品、同一版本、同一颜色出现页面直降时，可以申请补差价。
""",
        encoding="utf-8",
    )

    result = LocalKnowledgeSearch(tmp_path).search("数码产品保价规则")

    assert result["status"] == "success"
    assert result["data"]["results"][0]["title"] == "数码产品价保政策"
    assert result["data"]["query_plan"][0]["intent"] == "price_protection"
    assert result["data"]["index"]["routes"][0]["categories"] == ["policy", "product"]


def test_mcp_knowledge_search_uses_local_knowledge_cards(tmp_path: Path) -> None:
    card = tmp_path / "logistics" / "delivery.md"
    card.parent.mkdir()
    card.write_text(
        """---
title: 配送与运费规则
category: logistics
keywords:
  - 配送
  - 运费
---

配送范围、配送时效和运费会根据地区、商品和活动变化。
""",
        encoding="utf-8",
    )
    gateway = MockMCPGateway(knowledge_search=LocalKnowledgeSearch(tmp_path))

    result = asyncio.run(gateway.call_tool("knowledge.search", {"query": "配送范围和运费"}))

    assert result["status"] == "success"
    assert result["data"]["results"][0]["title"] == "配送与运费规则"
    assert result["data"]["results"][0]["source"] == "logistics/delivery.md"
    assert result["data"]["results"][0]["source"] != "mock_knowledge_base"
