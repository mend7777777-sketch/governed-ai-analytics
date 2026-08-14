ALTER TABLE iam_users
  ADD COLUMN IF NOT EXISTS failed_login_attempts INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS locked_until DATETIME NULL,
  ADD COLUMN IF NOT EXISTS last_login_at DATETIME NULL;

CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  token_hash CHAR(64) NOT NULL UNIQUE,
  user_id BIGINT NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_refresh_token_active (user_id, revoked_at, expires_at)
);
