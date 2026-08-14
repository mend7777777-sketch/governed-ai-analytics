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
