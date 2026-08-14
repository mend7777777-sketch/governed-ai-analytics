CREATE TABLE IF NOT EXISTS access_policy_scopes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  role_name VARCHAR(100) NOT NULL,
  department_code VARCHAR(64) NULL,
  position_code VARCHAR(64) NULL,
  table_name VARCHAR(128) NOT NULL,
  allow_detail_query BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_access_scope (role_name, department_code, position_code, table_name)
);

CREATE INDEX idx_access_scope_user ON access_policy_scopes (department_code, position_code, role_name);
