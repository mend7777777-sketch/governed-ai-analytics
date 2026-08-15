-- Productization: knowledge versions, metric definitions, query history,
-- and richer metadata/audit state.

SET @schema_name = DATABASE();

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='knowledge_documents' AND column_name='document_key';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE knowledge_documents ADD COLUMN document_key VARCHAR(320) NULL', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='knowledge_documents' AND column_name='version_no';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE knowledge_documents ADD COLUMN version_no INT NOT NULL DEFAULT 1', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='knowledge_documents' AND column_name='is_current';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE knowledge_documents ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='knowledge_documents' AND column_name='deleted_at';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE knowledge_documents ADD COLUMN deleted_at DATETIME NULL', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='knowledge_documents' AND column_name='trained_at';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE knowledge_documents ADD COLUMN trained_at DATETIME NULL', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

UPDATE knowledge_documents
SET document_key=CONCAT(document_type, ':', title), version_no=1, is_current=TRUE
WHERE document_key IS NULL;
CREATE INDEX idx_knowledge_current ON knowledge_documents (document_key, is_current, deleted_at);

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

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='query_audit_logs' AND column_name='actor_user_id';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE query_audit_logs ADD COLUMN actor_user_id BIGINT NULL', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
