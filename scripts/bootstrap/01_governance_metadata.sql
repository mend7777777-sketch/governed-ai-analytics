-- Purpose: governed table and column metadata for AI Text2SQL.

CREATE TABLE IF NOT EXISTS metadata_tables (
  table_name VARCHAR(128) PRIMARY KEY,
  business_name VARCHAR(255) NOT NULL,
  owner_name VARCHAR(100) NOT NULL,
  sensitivity_level ENUM('PUBLIC','INTERNAL','SENSITIVE') NOT NULL DEFAULT 'INTERNAL',
  ai_query_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  approval_status ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metadata_columns (
  table_name VARCHAR(128) NOT NULL,
  column_name VARCHAR(128) NOT NULL,
  business_description TEXT,
  sensitivity_level ENUM('PUBLIC','INTERNAL','SENSITIVE') NOT NULL DEFAULT 'INTERNAL',
  ai_query_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (table_name, column_name)
);

CREATE TABLE IF NOT EXISTS access_policies (
  role_name VARCHAR(100) NOT NULL,
  table_name VARCHAR(128) NOT NULL,
  allow_detail_query BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (role_name, table_name)
);

CREATE TABLE IF NOT EXISTS query_audit_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  actor_role VARCHAR(100) NOT NULL,
  question_hash CHAR(64) NOT NULL,
  generated_sql TEXT,
  status VARCHAR(20) NOT NULL,
  elapsed_ms INT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Demo warehouse tables must exist before seeding this metadata.
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
