USE customer_service_agent;

DELETE FROM ticket_events WHERE ticket_id = 'TK-000001';
DELETE FROM tickets WHERE ticket_id = 'TK-000001';
DELETE FROM after_sales WHERE after_sales_id IN ('AS-202605200777-01', 'AS-202605280088-01');
DELETE FROM shipments WHERE order_id IN ('64575145823542368', '202606030001', '202605280088', '202605200777');
DELETE FROM payments WHERE order_id IN ('64575145823542368', '202606030001', '202605280088', '202605200777');
DELETE FROM order_items WHERE order_id IN ('64575145823542368', '202606030001', '202605280088', '202605200777');
DELETE FROM orders WHERE order_id IN ('64575145823542368', '202606030001', '202605280088', '202605200777');
DELETE FROM user_addresses WHERE user_id IN ('user_test', 'user_demo', 'user_vip');
DELETE FROM memberships WHERE user_id IN ('user_test', 'user_demo', 'user_vip');
DELETE FROM users WHERE user_id IN ('user_test', 'user_demo', 'user_vip');

INSERT INTO users (user_id, display_name, phone_masked, email_masked, preferred_language, account_status)
VALUES
  ('user_test', '测试用户', '138****8001', 'test***@example.com', 'zh-CN', 'active'),
  ('user_demo', '林小北', '139****2026', 'lin***@example.com', 'zh-CN', 'active'),
  ('user_vip', '周明', '136****7788', 'vip***@example.com', 'zh-CN', 'active')
ON DUPLICATE KEY UPDATE
  display_name = VALUES(display_name),
  phone_masked = VALUES(phone_masked),
  email_masked = VALUES(email_masked),
  account_status = VALUES(account_status);

INSERT INTO memberships (user_id, member_level, points, growth_value)
VALUES
  ('user_test', 'silver', 820, 1300),
  ('user_demo', 'gold', 2680, 5600),
  ('user_vip', 'black_gold', 12800, 36000)
ON DUPLICATE KEY UPDATE
  member_level = VALUES(member_level),
  points = VALUES(points),
  growth_value = VALUES(growth_value);

INSERT INTO user_addresses (
  user_id, receiver_name, phone_masked, province, city, district, address_masked, is_default
)
VALUES
  ('user_test', '测*', '138****8001', '上海市', '上海市', '浦东新区', '张江高科****号', TRUE),
  ('user_demo', '林*北', '139****2026', '北京市', '北京市', '朝阳区', '望京街道****室', TRUE),
  ('user_vip', '周*', '136****7788', '广东省', '深圳市', '南山区', '科技园****栋', TRUE);

INSERT INTO orders (order_id, user_id, order_status, total_amount, currency, created_at, paid_at, completed_at)
VALUES
  ('64575145823542368', 'user_test', 'shipping', 4999.00, 'CNY', '2026-06-01 10:20:00', '2026-06-01 10:25:00', NULL),
  ('202606030001', 'user_demo', 'paid_waiting_ship', 5599.00, 'CNY', '2026-06-03 09:12:00', '2026-06-03 09:13:00', NULL),
  ('202605280088', 'user_demo', 'completed', 899.00, 'CNY', '2026-05-28 14:30:00', '2026-05-28 14:32:00', '2026-05-31 18:05:00'),
  ('202605200777', 'user_vip', 'after_sales', 6999.00, 'CNY', '2026-05-20 20:00:00', '2026-05-20 20:02:00', NULL)
ON DUPLICATE KEY UPDATE
  order_status = VALUES(order_status),
  total_amount = VALUES(total_amount),
  paid_at = VALUES(paid_at),
  completed_at = VALUES(completed_at);

INSERT INTO order_items (order_id, product_sku, product_name, sku_name, quantity, unit_price)
VALUES
  ('64575145823542368', 'PHONE-X1-256-BLACK', 'Aurora Phone X1', '12GB+256GB 曜石黑', 1, 4999.00),
  ('202606030001', 'PHONE-X1-512-BLUE', 'Aurora Phone X1', '12GB+512GB 极光蓝', 1, 5599.00),
  ('202605280088', 'BUDS-PRO-WHITE', 'SonicBuds Pro', '云白色', 1, 899.00),
  ('202605200777', 'BOOK-AIR14-512-SILVER', 'PowerBook Air 14', '16GB+512GB 月岩银', 1, 6999.00);

INSERT INTO payments (order_id, payment_status, payment_method, paid_amount, transaction_id, paid_at)
VALUES
  ('64575145823542368', 'paid', 'alipay', 4999.00, 'PAY202606010001', '2026-06-01 10:25:00'),
  ('202606030001', 'paid', 'wechat_pay', 5599.00, 'PAY202606030001', '2026-06-03 09:13:00'),
  ('202605280088', 'paid', 'credit_card', 899.00, 'PAY202605280088', '2026-05-28 14:32:00'),
  ('202605200777', 'paid', 'installment', 6999.00, 'PAY202605200777', '2026-05-20 20:02:00')
ON DUPLICATE KEY UPDATE
  payment_status = VALUES(payment_status),
  payment_method = VALUES(payment_method),
  paid_amount = VALUES(paid_amount);

INSERT INTO shipments (
  order_id, logistics_status, carrier, tracking_number, estimated_delivery_time,
  last_update, shipped_at, delivered_at
)
VALUES
  ('64575145823542368', 'out_for_delivery', '顺丰速运', 'SF202606010888', '今天 18:00 前', '包裹已到达所在城市，正在派送中。', '2026-06-02 08:00:00', NULL),
  ('202606030001', 'warehouse_processing', '平台仓配', NULL, '预计 2026-06-04 发出', '订单已支付，仓库正在配货。', NULL, NULL),
  ('202605280088', 'delivered', '京东物流', 'JD202605280088', '已签收', '包裹已由本人签收。', '2026-05-29 09:15:00', '2026-05-31 18:05:00'),
  ('202605200777', 'exception', '顺丰速运', 'SF202605200777', '异常处理中', '用户反馈外包装破损，已进入售后核验。', '2026-05-21 09:00:00', NULL)
ON DUPLICATE KEY UPDATE
  logistics_status = VALUES(logistics_status),
  carrier = VALUES(carrier),
  tracking_number = VALUES(tracking_number),
  estimated_delivery_time = VALUES(estimated_delivery_time),
  last_update = VALUES(last_update);

INSERT INTO after_sales (after_sales_id, order_id, user_id, service_type, status, reason)
VALUES
  ('AS-202605200777-01', '202605200777', 'user_vip', 'exchange', 'reviewing', '外包装破损，设备边角磕碰'),
  ('AS-202605280088-01', '202605280088', 'user_demo', 'invoice', 'completed', '申请补开发票')
ON DUPLICATE KEY UPDATE
  status = VALUES(status),
  reason = VALUES(reason);

INSERT INTO tickets (ticket_id, user_id, conversation_id, case_type, title, description, priority, status, related_order_id)
VALUES
  ('TK-000001', 'user_vip', 'seed_conv_1', 'after_sales', 'PowerBook 外包装破损跟进', '用户反馈外包装破损，需核实换货。', 'high', 'processing', '202605200777')
ON DUPLICATE KEY UPDATE
  status = VALUES(status),
  description = VALUES(description);

INSERT INTO ticket_events (ticket_id, event_type, content)
VALUES
  ('TK-000001', 'created', '种子数据：工单已创建。');
