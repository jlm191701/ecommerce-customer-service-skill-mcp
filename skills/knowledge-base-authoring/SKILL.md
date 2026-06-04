---
name: knowledge-base-authoring
description: Generate, review, and maintain structured Markdown knowledge cards for the intelligent customer-service project. Use when Codex needs to add product parameters, pricing, warranty, price-protection, promotion, logistics, billing, after-sales, compatibility, or FAQ content under backend/knowledge so knowledge.search can retrieve it reliably.
---

# Knowledge Base Authoring

## Overview

Use this skill to create retrievable ecommerce knowledge cards for `backend/knowledge/**/*.md`. The output must be useful to customer-service replies and friendly to the OpenViking-lite retriever.

## Workflow

1. Identify the knowledge type: product, policy, promotion, after_sales, logistics, billing, account, compatibility, service, or order.
2. Choose a stable file path under `backend/knowledge/<category>/`.
3. Write one focused card per topic. Do not combine unrelated policies or multiple products in one card unless the user explicitly asks for a comparison card.
4. Add frontmatter with `title`, `category`, `keywords`, `updated_at`, and when useful `product_ids`, `tags`, `priority`.
5. Put the most answerable facts in the body: concrete parameters, applicability, exceptions, required user inputs, and escalation conditions.
6. Keep operational claims conservative. For refunds, compensation, exceptions, and account security, say what can be checked or applied for, not guaranteed outcomes.
7. After editing cards, run backend knowledge tests or at least probe `LocalKnowledgeSearch` with likely user queries.

## Card Shape

Read `references/card-schema.md` before creating new card families or when unsure about fields.

Minimum card:

```markdown
---
title: Aurora Phone X1 参数
category: product
keywords:
  - Aurora Phone X1
  - 快充
  - 参数
updated_at: 2026-06-03
product_ids:
  - aurora phone x1
priority: 0.8
---

Aurora Phone X1 支持最高 80W 有线快充，并支持 30W 无线充电。
```

## Writing Rules

- Put exact product names, aliases, model names, policy names, and common user wording in `keywords`.
- Use `product_ids` to connect parameter, price, compatibility, warranty, and promotion cards for the same product.
- Prefer concrete values: wattage, storage, price, warranty duration, price-protection window, delivery window, required proof.
- Include exceptions and limits in the body. This helps the agent avoid over-promising.
- Do not store personal user data, real credentials, private addresses, full phone numbers, or real order details in static knowledge cards.
- Do not write chatbot role prompts here. That belongs to `customer_service_core`.

## Validation

After adding cards, prefer:

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/test_knowledge_search.py
```

If a card should answer a known query, manually probe `LocalKnowledgeSearch` and confirm the expected card appears in the top results.
