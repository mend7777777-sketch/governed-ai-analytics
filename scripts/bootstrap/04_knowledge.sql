-- Purpose: business knowledge documents and Vanna/Chroma training status.

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  document_type VARCHAR(64) NOT NULL DEFAULT 'business_definition',
  content LONGTEXT NOT NULL,
  status ENUM('TRAINING','TRAINED','FAILED') NOT NULL DEFAULT 'TRAINING',
  training_id VARCHAR(255) NULL,
  error_message VARCHAR(1000) NULL,
  created_by BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  document_key VARCHAR(320) NULL,
  version_no INT NOT NULL DEFAULT 1,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  deleted_at DATETIME NULL,
  trained_at DATETIME NULL,
  INDEX idx_knowledge_current (document_key, is_current, deleted_at)
);

CREATE TABLE IF NOT EXISTS metric_definitions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  metric_code VARCHAR(128) NOT NULL,
  metric_name VARCHAR(255) NOT NULL,
  definition TEXT NOT NULL,
  sql_expression TEXT NULL,
  status ENUM('DRAFT','PUBLISHED','RETIRED') NOT NULL DEFAULT 'DRAFT',
  version_no INT NOT NULL DEFAULT 1,
  is_current BOOLEAN NOT NULL DEFAULT TRUE,
  created_by BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_metric_current (metric_code, is_current, status)
);

CREATE TABLE IF NOT EXISTS query_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  session_id VARCHAR(128) NULL,
  question TEXT NOT NULL,
  generated_sql TEXT NULL,
  status VARCHAR(20) NOT NULL,
  row_count INT NOT NULL DEFAULT 0,
  elapsed_ms INT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_query_history_user (user_id, created_at),
  INDEX idx_query_history_session (user_id, session_id, created_at)
);
