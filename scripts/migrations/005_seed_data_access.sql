-- Seed field metadata from the current warehouse schema.
INSERT IGNORE INTO metadata_columns (table_name, column_name, business_description, sensitivity_level, ai_query_enabled)
SELECT c.table_name, c.column_name, NULL, 'INTERNAL', TRUE
FROM information_schema.columns AS c
WHERE c.table_schema = DATABASE()
  AND c.table_name IN ('dim_date', 'dim_region', 'dim_product', 'dim_user', 'fact_orders', 'fact_payments');

UPDATE metadata_columns
SET business_description='用户姓名，默认不向 AI 问数开放', sensitivity_level='SENSITIVE', ai_query_enabled=FALSE
WHERE table_name='dim_user' AND column_name='user_name';

-- INSERT IGNORE avoids MySQL's INSERT ... SELECT / ON DUPLICATE KEY parser differences.
INSERT IGNORE INTO access_policies (role_name, table_name, allow_detail_query)
SELECT role_seed.role_name, table_seed.table_name, TRUE
FROM (
  SELECT 'data_analyst' AS role_name
  UNION ALL SELECT 'data_developer'
) AS role_seed
CROSS JOIN (
  SELECT 'dim_date' AS table_name
  UNION ALL SELECT 'dim_region'
  UNION ALL SELECT 'dim_product'
  UNION ALL SELECT 'dim_user'
  UNION ALL SELECT 'fact_orders'
  UNION ALL SELECT 'fact_payments'
) AS table_seed;

INSERT IGNORE INTO access_policies (role_name, table_name, allow_detail_query) VALUES
  ('business_user', 'dim_date', TRUE),
  ('business_user', 'dim_region', TRUE),
  ('business_user', 'dim_product', TRUE),
  ('business_user', 'fact_orders', TRUE);

UPDATE access_policies
SET allow_detail_query=TRUE
WHERE role_name IN ('data_analyst', 'data_developer')
  AND table_name IN ('dim_date', 'dim_region', 'dim_product', 'dim_user', 'fact_orders', 'fact_payments');
