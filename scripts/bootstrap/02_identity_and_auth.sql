-- Purpose: local users, organization, roles, permissions, audit, and login security.

CREATE TABLE IF NOT EXISTS iam_departments (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  department_code VARCHAR(64) NOT NULL UNIQUE,
  department_name VARCHAR(128) NOT NULL,
  parent_id BIGINT NULL,
  status ENUM('ACTIVE','DISABLED') NOT NULL DEFAULT 'ACTIVE'
);
CREATE TABLE IF NOT EXISTS iam_positions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  position_code VARCHAR(64) NOT NULL UNIQUE,
  position_name VARCHAR(128) NOT NULL
);
CREATE TABLE IF NOT EXISTS iam_users (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(128) NOT NULL UNIQUE,
  display_name VARCHAR(128) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  department_id BIGINT NULL,
  position_id BIGINT NULL,
  status ENUM('ACTIVE','LOCKED','DISABLED') NOT NULL DEFAULT 'ACTIVE',
  failed_login_attempts INT NOT NULL DEFAULT 0,
  locked_until DATETIME NULL,
  last_login_at DATETIME NULL,
  token_version INT NOT NULL DEFAULT 0,
  password_changed_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS iam_roles (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  role_code VARCHAR(64) NOT NULL UNIQUE,
  role_name VARCHAR(128) NOT NULL
);
CREATE TABLE IF NOT EXISTS iam_user_roles (user_id BIGINT NOT NULL, role_id BIGINT NOT NULL, PRIMARY KEY (user_id, role_id));
CREATE TABLE IF NOT EXISTS iam_role_permissions (role_id BIGINT NOT NULL, permission_code VARCHAR(128) NOT NULL, PRIMARY KEY (role_id, permission_code));
CREATE TABLE IF NOT EXISTS iam_audit_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY, actor_user_id BIGINT NULL, action_code VARCHAR(128) NOT NULL,
  target_type VARCHAR(64) NOT NULL, target_id VARCHAR(128) NULL, detail_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
  id BIGINT AUTO_INCREMENT PRIMARY KEY, token_hash CHAR(64) NOT NULL UNIQUE, user_id BIGINT NOT NULL,
  expires_at DATETIME NOT NULL, revoked_at DATETIME NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_refresh_token_active (user_id, revoked_at, expires_at)
);
CREATE TABLE IF NOT EXISTS auth_rate_limits (
  rate_key VARCHAR(255) PRIMARY KEY,
  attempt_count INT NOT NULL DEFAULT 0,
  window_started_at DATETIME NOT NULL,
  blocked_until DATETIME NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO iam_roles (role_code, role_name) VALUES
  ('platform_admin', '平台管理员'), ('data_analyst', '数据分析师'), ('data_developer', '数据开发'),
  ('business_user', '业务用户'), ('governance_approver', '治理审批员')
ON DUPLICATE KEY UPDATE role_name = VALUES(role_name);

INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT r.id, p.permission_code FROM iam_roles r
JOIN (SELECT 'analytics.query' permission_code UNION ALL SELECT 'governance.table.manage' UNION ALL SELECT 'governance.table.approve' UNION ALL SELECT 'iam.user.manage') p
WHERE r.role_code = 'platform_admin';
INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT r.id, 'analytics.query' FROM iam_roles r WHERE r.role_code IN ('data_analyst', 'data_developer', 'business_user');
INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT r.id, 'governance.table.approve' FROM iam_roles r WHERE r.role_code = 'governance_approver';
