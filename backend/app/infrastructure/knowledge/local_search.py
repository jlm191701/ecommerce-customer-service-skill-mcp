from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class KnowledgeCard:
    title: str
    category: str
    keywords: tuple[str, ...]
    body: str
    source: str
    updated_at: str | None
    modified_at: str
    tags: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    priority: float = 0.5

    @property
    def summary(self) -> str:
        text = " ".join(line.strip() for line in self.body.splitlines() if line.strip())
        if len(text) <= 160:
            return text
        return text[:157].rstrip() + "..."

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "category": self.category,
            "keywords": list(self.keywords),
            "body": self.body,
            "summary": self.summary,
            "source": self.source,
            "updated_at": self.updated_at,
            "modified_at": self.modified_at,
            "tags": list(self.tags),
            "product_ids": list(self.product_ids),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class TypedKnowledgeQuery:
    query: str
    intent: str
    categories: tuple[str, ...]
    priority: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "categories": list(self.categories),
            "priority": self.priority,
        }


class LocalKnowledgeSearch:
    """OpenViking-style local retriever for static customer-service resources.

    This is intentionally still a MCP tool implementation, not a skill. The
    skill decides when a product/policy lookup is needed; this retriever owns
    indexing, query planning, hierarchical recall, deterministic rerank, and
    provenance for static knowledge cards.
    """

    INDEX_VERSION = 5
    GLOBAL_SEARCH_TOPK = 12
    SCORE_THRESHOLD = 0.16

    CATEGORY_ALIASES = {
        "product": {
            "产品",
            "商品",
            "参数",
            "配置",
            "快充",
            "续航",
            "手机",
            "平板",
            "耳机",
            "路由器",
            "摄像头",
            "手表",
            "电脑",
        },
        "policy": {"政策", "规则", "价保", "保价", "退货", "换货", "保修", "质保", "隐私"},
        "promotion": {"活动", "优惠", "券", "优惠券", "分期", "套餐", "降价"},
        "after_sales": {"售后", "退款", "退货", "换货", "维修", "补发", "破损", "质量"},
        "logistics": {"物流", "配送", "运费", "地址", "签收", "快递", "派送"},
        "billing": {"支付", "付款", "发票", "开票", "税号", "扣款"},
        "account": {"账号", "登录", "会员", "积分", "隐私", "安全"},
        "compatibility": {"兼容", "适配", "充电器", "配件", "连接", "设置"},
        "service": {"人工", "客服", "投诉", "工作时间", "转人工"},
        "order": {"订单", "取消", "状态"},
    }

    PRODUCT_ALIASES = {
        "aurora phone x1": {"aurora phone x1", "x1", "aurora", "极光手机"},
        "aurora phone x1 pro": {"aurora phone x1 pro", "x1 pro", "极光 pro", "旗舰手机"},
        "aurora phone lite e": {"aurora phone lite e", "lite e", "入门手机", "老人机"},
        "nova pad 12": {"nova pad 12", "nova pad", "平板"},
        "nova tab kids": {"nova tab kids", "kids 平板", "儿童平板"},
        "powerbook air 14": {"powerbook air 14", "powerbook", "笔记本"},
        "powerbook pro 16": {"powerbook pro 16", "pro 16", "创作本", "高性能笔记本"},
        "sonicbuds pro": {"sonicbuds pro", "耳机"},
        "sonicbuds lite": {"sonicbuds lite", "lite 耳机", "入耳耳机"},
        "router ax6000": {"router ax6000", "ax6000", "路由器"},
        "homehub matter": {"homehub matter", "matter 网关", "智能家居网关"},
        "smartwatch s5": {"smartwatch s5", "s5", "手表"},
        "visioncam mini": {"visioncam mini", "摄像头"},
        "gan charger 100w": {"gan charger 100w", "100w 氮化镓", "gan 充电器"},
    }

    QUERY_EXPANSIONS = {
        "价保": ("价保", "保价", "差价", "降价", "价格保护"),
        "保价": ("价保", "保价", "差价", "降价", "价格保护"),
        "快充": ("快充", "充电", "有线快充", "无线充电", "充电器"),
        "参数": ("参数", "配置", "规格", "性能"),
        "退货": ("退货", "退款", "退换货", "售后"),
        "换货": ("换货", "退换货", "售后", "补发"),
        "保修": ("保修", "维修", "质保", "售后"),
        "发票": ("发票", "开票", "抬头", "税号"),
        "物流": ("物流", "配送", "派送", "签收", "运费"),
        "以旧换新": ("以旧换新", "回收", "抵扣", "估价", "旧机"),
        "学生": ("学生", "教育优惠", "校园", "学生认证"),
        "电池": ("电池", "续航", "健康度", "充放电", "保养"),
        "屏幕": ("屏幕", "显示", "亮点", "坏点", "漏光", "触控"),
        "耳机": ("耳机", "降噪", "蓝牙", "佩戴", "充电盒"),
        "路由器": ("路由器", "wifi", "mesh", "组网", "信号"),
        "区别": ("区别", "对比", "差异", "选购", "适合", "推荐"),
        "对比": ("区别", "对比", "差异", "选购", "适合", "推荐"),
        "哪个": ("区别", "对比", "选购", "适合", "推荐"),
        "适合": ("选购", "推荐", "区别", "对比", "场景"),
        "2.4g": ("2.4g", "2.4ghz", "wifi", "网络", "配网"),
        "2.4G": ("2.4g", "2.4ghz", "wifi", "网络", "配网"),
        "5g": ("5g", "5ghz", "wifi", "网络", "配网"),
    }

    def __init__(self, knowledge_path: Path, limit: int = 3) -> None:
        self._knowledge_path = knowledge_path
        self._index_path = knowledge_path / ".index" / "knowledge_index.json"
        self._limit = limit
        self._index: dict[str, Any] | None = None

    def search(self, query: str, limit: int | None = None) -> dict[str, Any]:
        query = query.strip()
        index = self._ensure_index()
        if not query:
            return self._failed(query, "missing_query", "缺少检索问题，无法查询知识库。")

        query_plan = self._build_query_plan(query)
        if not query_plan:
            return self._failed(query, "missing_query", "缺少有效检索词，无法查询知识库。")

        card_scores: dict[str, float] = defaultdict(float)
        evidence_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        route_debug: list[dict[str, Any]] = []

        for typed_query in query_plan:
            recall = self._retrieve_for_typed_query(index, typed_query)
            route_debug.append(
                {
                    "query": typed_query.query,
                    "intent": typed_query.intent,
                    "categories": list(typed_query.categories),
                    "candidate_count": len(recall["card_scores"]),
                }
            )
            priority_weight = 1.0 + typed_query.priority * 0.08
            for source, score in recall["card_scores"].items():
                card_scores[source] = max(card_scores[source], score * priority_weight)
            for source, items in recall["evidence"].items():
                evidence_by_source[source].extend(items)

        reranked = [
            (
                source,
                self._rerank_card(
                    index["cards"][source],
                    query=query,
                    query_plan=query_plan,
                    recall_score=score,
                    evidence=evidence_by_source.get(source, []),
                    usage=index.setdefault("usage", {}).get(source, {}),
                ),
            )
            for source, score in card_scores.items()
            if source in index["cards"]
        ]
        reranked = [
            (source, score)
            for source, score in sorted(reranked, key=lambda item: item[1], reverse=True)
            if score >= self.SCORE_THRESHOLD
        ][: limit or self._limit]

        if not reranked:
            return self._failed(query, "not_found", "知识库暂时没有找到匹配结果。")

        results = [
            self._to_result(
                index,
                source,
                score,
                query,
                evidence_by_source.get(source, []),
            )
            for source, score in reranked
        ]
        self._record_usage(index, [source for source, _score in reranked])

        titles = "、".join(result["title"] for result in results)
        return {
            "tool": "knowledge.search",
            "status": "success",
            "data": {
                "query": query,
                "query_plan": [item.to_dict() for item in query_plan],
                "results": results,
                "index": {
                    "source": str(self._knowledge_path),
                    "path": str(self._index_path),
                    "cards": len(index["cards"]),
                    "records": len(index["records"]),
                    "method": "openviking_lite_query_plan_hierarchical_rerank",
                    "routes": route_debug,
                },
            },
            "display_summary": f"找到 {len(results)} 条相关知识：{titles}。",
            "suggested_next_actions": ["reply_to_user", "ask_follow_up_if_needed"],
            "permission": {"checked": True, "allowed": True},
        }

    def _retrieve_for_typed_query(
        self,
        index: dict[str, Any],
        typed_query: TypedKnowledgeQuery,
    ) -> dict[str, Any]:
        query_tokens = self._tokens(typed_query.query)
        if not query_tokens:
            return {"card_scores": {}, "evidence": {}}

        navigation_scores = self._score_records(index, query_tokens, levels={0, 1})
        selected_categories, selected_sources = self._select_scope(
            index,
            navigation_scores,
            typed_query.categories,
        )
        detail_scores = self._score_records(index, query_tokens, levels={2})
        scoped_detail_scores = self._filter_scores(
            index,
            detail_scores,
            selected_categories=selected_categories,
            selected_sources=selected_sources,
        )
        if not scoped_detail_scores:
            scoped_detail_scores = dict(
                sorted(detail_scores.items(), key=lambda item: item[1], reverse=True)[
                    : self.GLOBAL_SEARCH_TOPK
                ]
            )

        return {
            "card_scores": self._aggregate_card_scores(
                index,
                typed_query=typed_query,
                detail_scores=scoped_detail_scores,
                navigation_scores=navigation_scores,
            ),
            "evidence": self._evidence_from_scores(index, scoped_detail_scores),
        }

    def _ensure_index(self) -> dict[str, Any]:
        signature = self._signature()
        if self._index and self._index.get("signature") == signature:
            return self._index

        loaded = self._load_index(signature)
        if loaded:
            self._index = loaded
            return loaded

        rebuilt = self._build_index(signature)
        self._write_index(rebuilt)
        self._index = rebuilt
        return rebuilt

    def _load_index(self, signature: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not self._index_path.exists():
            return None
        try:
            loaded = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if loaded.get("version") != self.INDEX_VERSION:
            return None
        if loaded.get("signature") != signature:
            return None
        loaded.setdefault("usage", {})
        return loaded

    def _write_index(self, index: dict[str, Any]) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _signature(self) -> list[dict[str, Any]]:
        if not self._knowledge_path.exists():
            return []
        files = []
        for path in sorted(self._knowledge_path.rglob("*.md")):
            if not path.is_file():
                continue
            stat = path.stat()
            files.append(
                {
                    "path": path.relative_to(self._knowledge_path).as_posix(),
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            )
        return files

    def _build_index(self, signature: list[dict[str, Any]]) -> dict[str, Any]:
        cards = self._load_cards()
        records: dict[str, dict[str, Any]] = {}
        inverted: dict[str, dict[str, float]] = defaultdict(dict)

        def add_record(record: dict[str, Any], weighted_parts: list[tuple[str, float]]) -> None:
            record_id = record["id"]
            token_weights: dict[str, float] = defaultdict(float)
            for text, weight in weighted_parts:
                for token in self._tokens(text):
                    token_weights[token] += weight
            record["token_count"] = len(token_weights)
            records[record_id] = record
            for token, weight in token_weights.items():
                inverted[token][record_id] = round(weight, 4)

        by_category: dict[str, list[KnowledgeCard]] = defaultdict(list)
        for card in cards:
            by_category[card.category].append(card)

        for category, category_cards in by_category.items():
            add_record(
                {
                    "id": f"l0:{category}",
                    "level": 0,
                    "category": category,
                    "source": "",
                    "title": category,
                    "abstract": "、".join(card.title for card in category_cards),
                    "is_leaf": False,
                },
                [
                    (category, 2.0),
                    (" ".join(self.CATEGORY_ALIASES.get(category, set())), 2.0),
                    (" ".join(card.title for card in category_cards), 1.0),
                    (" ".join(" ".join(card.keywords) for card in category_cards), 1.0),
                ],
            )

        for card in cards:
            add_record(
                {
                    "id": f"l1:{card.source}",
                    "level": 1,
                    "category": card.category,
                    "source": card.source,
                    "title": card.title,
                    "abstract": card.summary,
                    "is_leaf": False,
                },
                [
                    (card.title, 5.0),
                    (" ".join(card.keywords), 4.0),
                    (" ".join(card.tags), 2.0),
                    (" ".join(card.product_ids), 2.0),
                    (card.category, 1.8),
                    (card.summary, 1.0),
                ],
            )
            for index, chunk in enumerate(self._chunks(card.body)):
                add_record(
                    {
                        "id": f"l2:{card.source}:{index}",
                        "level": 2,
                        "category": card.category,
                        "source": card.source,
                        "title": card.title,
                        "abstract": chunk,
                        "is_leaf": True,
                    },
                    [
                        (chunk, 1.0),
                        (card.title, 0.35),
                        (" ".join(card.keywords), 0.7),
                        (" ".join(card.tags), 0.35),
                        (" ".join(card.product_ids), 0.4),
                    ],
                )

        document_count = max(len(records), 1)
        document_frequency = {token: len(postings) for token, postings in inverted.items()}

        return {
            "version": self.INDEX_VERSION,
            "signature": signature,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "cards": {card.source: card.to_dict() for card in cards},
            "records": records,
            "inverted": {token: postings for token, postings in inverted.items()},
            "document_count": document_count,
            "document_frequency": document_frequency,
            "usage": {},
        }

    def _load_cards(self) -> list[KnowledgeCard]:
        if not self._knowledge_path.exists():
            return []

        cards: list[KnowledgeCard] = []
        for path in sorted(self._knowledge_path.rglob("*.md")):
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8")
            meta, body = self._parse_markdown(raw)
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            title = str(meta.get("title") or path.stem).strip()
            category = str(meta.get("category") or path.parent.name).strip()
            keywords = self._coerce_list(meta.get("keywords"))
            tags = self._coerce_list(meta.get("tags"))
            product_ids = self._coerce_list(meta.get("product_ids"))
            if not product_ids:
                product_ids = self._infer_product_ids(f"{title} {' '.join(keywords)} {body}")
            updated_at = self._parse_date(meta.get("updated_at"))
            priority = self._coerce_priority(meta.get("priority"))
            cards.append(
                KnowledgeCard(
                    title=title,
                    category=category,
                    keywords=tuple(keywords),
                    body=body.strip(),
                    source=path.relative_to(self._knowledge_path).as_posix(),
                    updated_at=updated_at.isoformat() if updated_at else None,
                    modified_at=modified_at.isoformat(),
                    tags=tuple(tags),
                    product_ids=tuple(product_ids),
                    priority=priority,
                )
            )
        return cards

    def _build_query_plan(self, query: str) -> list[TypedKnowledgeQuery]:
        base_tokens = self._tokens(query)
        if not base_tokens:
            return []

        categories = self._infer_categories(query)
        intent = self._infer_intent(query, categories)
        expanded_terms = self._expand_terms(query)
        queries = [
            TypedKnowledgeQuery(
                query=query,
                intent=intent,
                categories=tuple(categories),
                priority=5,
            )
        ]

        if expanded_terms != query:
            queries.append(
                TypedKnowledgeQuery(
                    query=expanded_terms,
                    intent=f"{intent}_expanded",
                    categories=tuple(categories),
                    priority=4,
                )
            )

        product_query = self._product_query(query)
        if product_query:
            product_categories = tuple(dict.fromkeys([*categories, "product", "compatibility"]))
            queries.append(
                TypedKnowledgeQuery(
                    query=product_query,
                    intent="product_resource",
                    categories=product_categories,
                    priority=4,
                )
            )

        if "policy" not in categories and any(word in query for word in ["规则", "政策", "价保", "保修", "退货"]):
            queries.append(
                TypedKnowledgeQuery(
                    query=f"{query} 政策 规则 适用条件",
                    intent="policy_resource",
                    categories=tuple(dict.fromkeys([*categories, "policy", "promotion"])),
                    priority=3,
                )
            )
        return self._dedupe_queries(queries)

    def _infer_categories(self, query: str) -> list[str]:
        normalized = query.lower()
        scores: dict[str, int] = defaultdict(int)
        for category, aliases in self.CATEGORY_ALIASES.items():
            for alias in aliases:
                if alias.lower() in normalized:
                    scores[category] += 1
        if re.search(r"\b\d{8,32}\b", query):
            scores["order"] += 2
            scores["logistics"] += 1
        for product, aliases in self.PRODUCT_ALIASES.items():
            if any(alias.lower() in normalized for alias in aliases):
                scores["product"] += 2
                if any(word in normalized for word in ["充电", "快充", "适配", "兼容"]):
                    scores["compatibility"] += 1
                if any(word in normalized for word in ["价格", "多少钱", "价保", "保价"]):
                    scores["policy"] += 1
                    scores["promotion"] += 1
                break
        if not scores:
            return []
        return [
            category
            for category, _score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[
                :4
            ]
        ]

    @staticmethod
    def _infer_intent(query: str, categories: list[str]) -> str:
        if any(word in query for word in ["价保", "保价", "差价", "降价"]):
            return "price_protection"
        if any(word in query for word in ["快充", "参数", "配置", "多少钱", "价格"]):
            return "product_question"
        if any(word in query for word in ["区别", "对比", "哪个", "适合", "推荐"]):
            return "product_comparison"
        if any(word in query for word in ["退货", "换货", "退款", "维修", "保修"]):
            return "after_sales_policy"
        if any(word in query for word in ["物流", "配送", "运费", "地址"]):
            return "logistics_policy"
        if categories:
            return f"{categories[0]}_resource"
        return "general_resource"

    def _expand_terms(self, query: str) -> str:
        terms = [query]
        for trigger, expansions in self.QUERY_EXPANSIONS.items():
            if trigger in query:
                terms.extend(expansions)
        return " ".join(dict.fromkeys(terms))

    def _product_query(self, query: str) -> str:
        normalized = query.lower()
        matched = []
        for product, aliases in self.PRODUCT_ALIASES.items():
            if any(alias.lower() in normalized for alias in aliases):
                matched.extend([product, *aliases])
        return " ".join(dict.fromkeys(matched))

    @staticmethod
    def _dedupe_queries(queries: list[TypedKnowledgeQuery]) -> list[TypedKnowledgeQuery]:
        seen: set[tuple[str, str]] = set()
        deduped = []
        for query in queries:
            key = (query.query, query.intent)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(query)
        return deduped[:5]

    def _score_records(
        self,
        index: dict[str, Any],
        query_tokens: set[str],
        levels: set[int],
    ) -> dict[str, float]:
        raw_scores: dict[str, float] = defaultdict(float)
        document_count = max(index.get("document_count") or len(index["records"]), 1)
        document_frequency = index.get("document_frequency") or {}
        for token in query_tokens:
            frequency = max(int(document_frequency.get(token) or 0), 0)
            idf = 1.0 + math.log((document_count + 1) / (frequency + 1))
            for record_id, weight in index["inverted"].get(token, {}).items():
                record = index["records"].get(record_id)
                if record and record["level"] in levels:
                    raw_scores[record_id] += float(weight) * idf

        scores = {}
        denominator = math.sqrt(max(len(query_tokens), 1))
        for record_id, score in raw_scores.items():
            scores[record_id] = round(score / denominator, 4)
        return scores

    def _select_scope(
        self,
        index: dict[str, Any],
        navigation_scores: dict[str, float],
        routed_categories: tuple[str, ...],
    ) -> tuple[set[str], set[str]]:
        selected_categories: set[str] = set(routed_categories)
        selected_sources: set[str] = set()
        ranked = sorted(navigation_scores.items(), key=lambda item: item[1], reverse=True)
        for record_id, score in ranked[:8]:
            if score <= 0:
                continue
            record = index["records"][record_id]
            if record["level"] == 0:
                selected_categories.add(record["category"])
            elif record["level"] == 1:
                selected_sources.add(record["source"])
                selected_categories.add(record["category"])
        return selected_categories, selected_sources

    @staticmethod
    def _filter_scores(
        index: dict[str, Any],
        scores: dict[str, float],
        selected_categories: set[str],
        selected_sources: set[str],
    ) -> dict[str, float]:
        if not selected_categories and not selected_sources:
            return scores
        filtered = {}
        for record_id, score in scores.items():
            record = index["records"][record_id]
            if record["source"] in selected_sources or record["category"] in selected_categories:
                filtered[record_id] = score
        return filtered

    def _aggregate_card_scores(
        self,
        index: dict[str, Any],
        typed_query: TypedKnowledgeQuery,
        detail_scores: dict[str, float],
        navigation_scores: dict[str, float],
    ) -> dict[str, float]:
        card_scores: dict[str, float] = defaultdict(float)
        category_scores: dict[str, float] = {}
        overview_scores: dict[str, float] = {}

        for record_id, score in navigation_scores.items():
            record = index["records"][record_id]
            if record["level"] == 0:
                category_scores[record["category"]] = max(
                    category_scores.get(record["category"], 0.0),
                    score,
                )
            elif record["level"] == 1:
                overview_scores[record["source"]] = max(
                    overview_scores.get(record["source"], 0.0),
                    score,
                )

        for record_id, score in detail_scores.items():
            record = index["records"][record_id]
            source = record["source"]
            card = index["cards"][source]
            route_boost = 1.0 if card["category"] in typed_query.categories else 0.0
            combined = (
                score
                + overview_scores.get(source, 0.0) * 0.75
                + category_scores.get(record["category"], 0.0) * 0.12
                + route_boost * 0.35
                + float(card.get("priority", 0.5)) * 0.08
            )
            card_scores[source] = max(card_scores[source], round(combined, 4))

        if not card_scores:
            for source, score in overview_scores.items():
                card = index["cards"][source]
                route_boost = 0.3 if card["category"] in typed_query.categories else 0.0
                card_scores[source] = round(
                    score + route_boost + float(card.get("priority", 0.5)) * 0.08,
                    4,
                )
        return card_scores

    def _rerank_card(
        self,
        card: dict[str, Any],
        query: str,
        query_plan: list[TypedKnowledgeQuery],
        recall_score: float,
        evidence: list[dict[str, Any]],
        usage: dict[str, Any],
    ) -> float:
        query_tokens = self._tokens(" ".join([query, *[item.query for item in query_plan]]))
        title_tokens = self._tokens(card["title"])
        keyword_tokens = self._tokens(" ".join(card.get("keywords", [])))
        body_tokens = self._tokens(card.get("summary") or card.get("body") or "")
        category_hits = sum(1 for item in query_plan if card["category"] in item.categories)

        title_overlap = self._overlap(query_tokens, title_tokens)
        keyword_overlap = self._overlap(query_tokens, keyword_tokens)
        body_overlap = self._overlap(query_tokens, body_tokens)
        exact_bonus = self._exact_phrase_bonus(query, card)
        scenario_bonus = self._scenario_bonus(query, card)
        evidence_bonus = min(len(evidence), 3) * 0.04
        hotness = self._hotness_score(card, usage)

        return round(
            recall_score * 0.58
            + title_overlap * 0.22
            + keyword_overlap * 0.16
            + body_overlap * 0.08
            + category_hits * 0.08
            + exact_bonus
            + scenario_bonus
            + evidence_bonus
            + hotness * 0.08,
            4,
        )

    @staticmethod
    def _overlap(query_tokens: set[str], target_tokens: set[str]) -> float:
        if not query_tokens or not target_tokens:
            return 0.0
        return len(query_tokens & target_tokens) / max(len(query_tokens), 1)

    def _exact_phrase_bonus(self, query: str, card: dict[str, Any]) -> float:
        normalized = query.lower()
        haystack = " ".join(
            [
                card.get("title", ""),
                " ".join(card.get("keywords", [])),
                " ".join(card.get("product_ids", [])),
            ]
        ).lower()
        bonus = 0.0
        for product, aliases in self.PRODUCT_ALIASES.items():
            if any(alias.lower() in normalized for alias in aliases) and product in haystack:
                bonus += 0.25
        for phrase in [
            "价保",
            "保价",
            "快充",
            "保修",
            "退货",
            "发票",
            "物流",
            "区别",
            "对比",
            "选购",
            "适合",
            "2.4ghz",
            "2.4g",
            "配网",
        ]:
            if phrase in normalized and phrase in haystack:
                bonus += 0.12
        return min(bonus, 0.45)

    def _scenario_bonus(self, query: str, card: dict[str, Any]) -> float:
        normalized = query.lower()
        title = str(card.get("title") or "")
        category = str(card.get("category") or "")
        tags = {str(tag).lower() for tag in card.get("tags", [])}
        keywords = " ".join(str(keyword).lower() for keyword in card.get("keywords", []))
        matched_products = {
            product
            for product, aliases in self.PRODUCT_ALIASES.items()
            if any(alias.lower() in normalized for alias in aliases)
        }
        card_products = {str(product).lower() for product in card.get("product_ids", [])}
        product_scope_ok = not matched_products or bool(matched_products & card_products)
        bonus = 0.0
        if any(word in normalized for word in ["区别", "对比", "哪个", "适合", "推荐"]):
            if product_scope_ok and (
                "comparison" in tags or any(word in title for word in ["区别", "对比"])
            ):
                bonus += 36.0
        if any(word in normalized for word in ["2.4g", "2.4ghz", "5g", "5ghz", "配网", "联网", "网络"]):
            if category == "compatibility" and any(
                word in keywords for word in ["2.4g", "2.4ghz", "wifi", "网络", "配网"]
            ):
                bonus += 18.0
        if any(word in normalized for word in ["凭证", "图片", "照片", "截图", "看图"]):
            if category in {"service", "after_sales"} and any(
                word in keywords for word in ["图片", "照片", "凭证", "截图"]
            ):
                bonus += 12.0
        return bonus

    @staticmethod
    def _evidence_from_scores(
        index: dict[str, Any],
        detail_scores: dict[str, float],
    ) -> dict[str, list[dict[str, Any]]]:
        evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record_id, score in sorted(detail_scores.items(), key=lambda item: item[1], reverse=True):
            record = index["records"][record_id]
            source = record["source"]
            if len(evidence[source]) >= 3:
                continue
            evidence[source].append(
                {
                    "record_id": record_id,
                    "level": record["level"],
                    "score": round(score, 4),
                    "text": record["abstract"],
                }
            )
        return evidence

    def _record_usage(self, index: dict[str, Any], sources: list[str]) -> None:
        usage = index.setdefault("usage", {})
        now = datetime.now(timezone.utc).isoformat()
        for source in sources:
            item = usage.setdefault(source, {"active_count": 0})
            item["active_count"] = int(item.get("active_count") or 0) + 1
            item["last_accessed_at"] = now
        self._write_index(index)

    def _hotness_score(self, card: dict[str, Any], usage: dict[str, Any]) -> float:
        active_count = int(usage.get("active_count") or 0)
        raw_updated = usage.get("last_accessed_at") or card.get("updated_at") or card.get("modified_at")
        try:
            updated = datetime.fromisoformat(str(raw_updated))
        except (TypeError, ValueError):
            return 0.0
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = max((now - updated).total_seconds() / 86400.0, 0.0)
        freq = 1.0 / (1.0 + math.exp(-math.log1p(active_count)))
        recency = math.exp(-(math.log(2) / 30.0) * age_days)
        return max(0.0, min(1.0, freq * recency))

    @staticmethod
    def _chunks(body: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
        chunks: list[str] = []
        for paragraph in paragraphs or [body.strip()]:
            if len(paragraph) <= 360:
                chunks.append(paragraph)
                continue
            sentences = re.split(r"(?<=[。！？.!?])\s*", paragraph)
            buffer = ""
            for sentence in sentences:
                if len(buffer) + len(sentence) <= 360:
                    buffer += sentence
                else:
                    if buffer:
                        chunks.append(buffer)
                    buffer = sentence
            if buffer:
                chunks.append(buffer)
        return chunks

    @staticmethod
    def _parse_markdown(raw: str) -> tuple[dict[str, Any], str]:
        if not raw.startswith("---"):
            return {}, raw
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, flags=re.DOTALL)
        if not match:
            return {}, raw

        meta: dict[str, Any] = {}
        current_key: str | None = None
        for line in match.group(1).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("-") and current_key:
                meta.setdefault(current_key, []).append(stripped[1:].strip())
                continue
            key, sep, value = stripped.partition(":")
            if not sep:
                current_key = None
                continue
            current_key = key.strip()
            value = value.strip()
            meta[current_key] = value if value else []

        return meta, match.group(2)

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,，、]", value) if item.strip()]
        return []

    @staticmethod
    def _coerce_priority(value: Any) -> float:
        if value is None or value == "":
            return 0.5
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _infer_product_ids(self, text: str) -> list[str]:
        normalized = text.lower()
        matches = []
        for product, aliases in self.PRODUCT_ALIASES.items():
            if any(alias.lower() in normalized for alias in aliases):
                matches.append(product)
        return matches

    @staticmethod
    def _tokens(text: str) -> set[str]:
        stopwords = {
            "什么",
            "怎么",
            "如何",
            "是否",
            "可以",
            "一下",
            "查询",
            "规则",
            "政策",
            "说明",
            "的是",
            "是什",
            "则是",
            "现在",
            "我的",
            "支持",
            "需要",
        }
        normalized = text.lower()
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
        for run in chinese_runs:
            if len(run) == 1:
                tokens.add(run)
                continue
            for size in (2, 3, 4):
                if len(run) < size:
                    continue
                for index in range(len(run) - size + 1):
                    tokens.add(run[index : index + size])
        return {token for token in tokens if token not in stopwords}

    def _to_result(
        self,
        index: dict[str, Any],
        source: str,
        score: float,
        query: str,
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        card = index["cards"][source]
        return {
            "title": card["title"],
            "category": card["category"],
            "summary": card["summary"],
            "source": card["source"],
            "score": score,
            "level": 2,
            "keywords": list(card["keywords"]),
            "evidence": self._trim_evidence(evidence),
            "relations": self._related_cards(index, card, exclude_source=source),
            "match_reason": self._match_reason(query, card, evidence),
        }

    @staticmethod
    def _trim_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trimmed = []
        seen = set()
        for item in evidence:
            text = " ".join(str(item.get("text") or "").split())
            if not text or text in seen:
                continue
            seen.add(text)
            trimmed.append(
                {
                    "score": item.get("score", 0.0),
                    "text": text[:220] + ("..." if len(text) > 220 else ""),
                }
            )
            if len(trimmed) >= 2:
                break
        return trimmed

    @staticmethod
    def _related_cards(
        index: dict[str, Any],
        card: dict[str, Any],
        exclude_source: str,
    ) -> list[dict[str, str]]:
        related = []
        product_ids = set(card.get("product_ids") or [])
        for source, other in index["cards"].items():
            if source == exclude_source:
                continue
            same_category = other.get("category") == card.get("category")
            same_product = product_ids and product_ids & set(other.get("product_ids") or [])
            if not same_category and not same_product:
                continue
            related.append(
                {
                    "title": other["title"],
                    "source": other["source"],
                    "relation": "same_product" if same_product else "same_category",
                }
            )
            if len(related) >= 3:
                break
        return related

    @staticmethod
    def _match_reason(query: str, card: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
        if evidence:
            return "命中标题/关键词后，在正文片段中找到可回答该问题的证据。"
        if any(keyword in query for keyword in card.get("keywords", [])):
            return "命中知识卡片关键词。"
        return "命中相关分类或产品资源。"

    @staticmethod
    def _failed(query: str, error_code: str, summary: str) -> dict[str, Any]:
        return {
            "tool": "knowledge.search",
            "status": "failed",
            "error_code": error_code,
            "data": {
                "query": query,
                "results": [],
            },
            "display_summary": summary,
            "suggested_next_actions": ["ask_follow_up_if_needed", "human_handoff"],
            "permission": {"checked": True, "allowed": True},
        }
