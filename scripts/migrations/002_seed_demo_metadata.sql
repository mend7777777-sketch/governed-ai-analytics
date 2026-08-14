INSERT INTO metadata_tables (table_name, business_name, owner_name, sensitivity_level, ai_query_enabled, approval_status)
VALUES
  ('dim_date', '日期维度', 'data-platform', 'PUBLIC', TRUE, 'APPROVED'),
  ('dim_region', '区域维度', 'data-platform', 'INTERNAL', TRUE, 'APPROVED'),
  ('dim_product', '商品维度', 'data-platform', 'INTERNAL', TRUE, 'APPROVED'),
  ('dim_user', '用户维度', 'data-platform', 'SENSITIVE', TRUE, 'APPROVED'),
  ('fact_orders', '订单事实表', 'commerce-analytics', 'SENSITIVE', TRUE, 'APPROVED'),
  ('fact_payments', '支付事实表', 'finance-analytics', 'SENSITIVE', TRUE, 'APPROVED')
ON DUPLICATE KEY UPDATE
  business_name = VALUES(business_name), owner_name = VALUES(owner_name),
  sensitivity_level = VALUES(sensitivity_level), ai_query_enabled = VALUES(ai_query_enabled),
  approval_status = VALUES(approval_status);
