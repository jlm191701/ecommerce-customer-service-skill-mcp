# Knowledge Card Schema

## Frontmatter

Use YAML frontmatter at the top of every Markdown card.

Required fields:

```yaml
title: Human-readable title
category: product
keywords:
  - user wording
  - product alias
updated_at: 2026-06-03
```

Optional fields:

```yaml
product_ids:
  - aurora phone x1
tags:
  - warranty
  - ecommerce
priority: 0.8
```

## Categories

Use one of these broad categories where possible:

- `product`: product parameters, model differences, price, stock, usage.
- `policy`: platform or category-level rules, including price protection, warranty, privacy, return limits.
- `promotion`: coupons, bundles, installment, campaign rules.
- `after_sales`: refund, return, exchange, repair, quality issue handling.
- `logistics`: delivery scope, shipping fee, address change, tracking delay, lost package.
- `billing`: payment, invoice, refund invoice.
- `account`: login, member level, privacy and account security.
- `compatibility`: chargers, accessories, router setup, device compatibility.
- `service`: handoff, complaint, working hours.
- `order`: general order status and cancellation rules.

Existing older cards may use narrower categories such as `product_phone`. New cards should prefer broad categories unless a narrow category is intentionally useful.

## Body Pattern

For product cards:

1. Product identity and positioning.
2. Concrete specs or price.
3. Included accessories or compatibility.
4. Conditions and caveats.
5. Recommended follow-up question if needed.

For policy cards:

1. Applicability.
2. Time window or threshold.
3. Required user information or proof.
4. Exclusions.
5. When to transfer to human support.

## Retrieval Tips

- Add common aliases in `keywords`: Chinese names, English names, abbreviations, model numbers.
- Use `product_ids` consistently across cards for the same product.
- Repeat the key answer in body text, not only in metadata.
- Keep one card focused; broad cards are harder to rank.
- Prefer stable facts over marketing copy.
