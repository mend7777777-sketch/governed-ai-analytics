-- Add token invalidation, password lifecycle, and database-backed login rate limits.
-- Compatible with MySQL 8 versions that do not support ADD COLUMN IF NOT EXISTS.

SET @schema_name = DATABASE();

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='iam_users' AND column_name='token_version';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE iam_users ADD COLUMN token_version INT NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists FROM information_schema.columns
WHERE table_schema=@schema_name AND table_name='iam_users' AND column_name='password_changed_at';
SET @statement = IF(@column_exists=0,
  'ALTER TABLE iam_users ADD COLUMN password_changed_at DATETIME NULL', 'SELECT 1');
PREPARE migration_statement FROM @statement; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

CREATE TABLE IF NOT EXISTS auth_rate_limits (
  rate_key VARCHAR(255) PRIMARY KEY,
  attempt_count INT NOT NULL DEFAULT 0,
  window_started_at DATETIME NOT NULL,
  blocked_until DATETIME NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
