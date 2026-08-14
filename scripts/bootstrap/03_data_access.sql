-- Purpose: table, column, organization scope, and row-level data access.
-- Run 01_governance_metadata.sql and 02_identity_and_auth.sql first.

INSERT IGNORE INTO metadata_columns (table_name, column_name, business_description, sensitivity_level, ai_query_enabled)
SELECT c.table_name, c.column_name, NULL, 'INTERNAL', TRUE
FROM information_schema.columns AS c
WHERE c.table_schema = DATABASE()
  AND c.table_name IN ('dim_date', 'dim_region', 'dim_product', 'dim_user', 'fact_orders', 'fact_payments');

UPDATE metadata_columns
SET business_description='用户姓名，默认不向 AI 问数开放', sensitivity_level='SENSITIVE', ai_query_enabled=FALSE
WHERE table_name='dim_user' AND column_name='user_name';

-- Generic table permissions by role.
INSERT IGNORE INTO access_policies (role_name, table_name, allow_detail_query)
SELECT role_seed.role_name, table_seed.table_name, TRUE
FROM (SELECT 'data_analyst' AS role_name UNION ALL SELECT 'data_developer') AS role_seed
CROSS JOIN (
  SELECT 'dim_date' AS table_name UNION ALL SELECT 'dim_region' UNION ALL SELECT 'dim_product'
  UNION ALL SELECT 'dim_user' UNION ALL SELECT 'fact_orders' UNION ALL SELECT 'fact_payments'
) AS table_seed;
INSERT IGNORE INTO access_policies (role_name, table_name, allow_detail_query) VALUES
  ('business_user', 'dim_date', TRUE), ('business_user', 'dim_region', TRUE),
  ('business_user', 'dim_product', TRUE), ('business_user', 'fact_orders', TRUE);

CREATE TABLE IF NOT EXISTS access_policy_scopes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  role_name VARCHAR(100) NOT NULL,
  department_code VARCHAR(64) NULL,
  position_code VARCHAR(64) NULL,
  table_name VARCHAR(128) NOT NULL,
  allow_detail_query BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_access_scope (role_name, department_code, position_code, table_name),
  INDEX idx_access_scope_user (department_code, position_code, role_name)
);

CREATE TABLE IF NOT EXISTS access_row_filters (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  role_name VARCHAR(100) NOT NULL,
  department_code VARCHAR(64) NULL,
  position_code VARCHAR(64) NULL,
  table_name VARCHAR(128) NOT NULL,
  column_name VARCHAR(128) NOT NULL,
  allowed_values_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_row_filter_scope (role_name, department_code, position_code, table_name, column_name)
);
