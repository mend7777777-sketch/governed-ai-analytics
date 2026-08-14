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
