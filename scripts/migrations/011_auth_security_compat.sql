-- Compatibility migration for MySQL 8 versions that do not support
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

SET @schema_name = DATABASE();

SELECT COUNT(*) INTO @column_exists
FROM information_schema.columns
WHERE table_schema = @schema_name AND table_name = 'iam_users' AND column_name = 'failed_login_attempts';
SET @statement = IF(@column_exists = 0,
  'ALTER TABLE iam_users ADD COLUMN failed_login_attempts INT NOT NULL DEFAULT 0',
  'SELECT 1');
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists
FROM information_schema.columns
WHERE table_schema = @schema_name AND table_name = 'iam_users' AND column_name = 'locked_until';
SET @statement = IF(@column_exists = 0,
  'ALTER TABLE iam_users ADD COLUMN locked_until DATETIME NULL',
  'SELECT 1');
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SELECT COUNT(*) INTO @column_exists
FROM information_schema.columns
WHERE table_schema = @schema_name AND table_name = 'iam_users' AND column_name = 'last_login_at';
SET @statement = IF(@column_exists = 0,
  'ALTER TABLE iam_users ADD COLUMN last_login_at DATETIME NULL',
  'SELECT 1');
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  token_hash CHAR(64) NOT NULL UNIQUE,
  user_id BIGINT NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_refresh_token_active (user_id, revoked_at, expires_at)
);
DESCRIBE iam_users;

SELECT failed_login_attempts, locked_until, last_login_at
FROM iam_users
WHERE username = 'admin';

SHOW TABLES LIKE 'auth_refresh_tokens';
