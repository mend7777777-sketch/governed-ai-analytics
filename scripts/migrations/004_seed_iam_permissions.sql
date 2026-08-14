INSERT INTO iam_roles (role_code, role_name) VALUES
  ('platform_admin', '平台管理员'),
  ('data_analyst', '数据分析师'),
  ('data_developer', '数据开发'),
  ('business_user', '业务用户'),
  ('governance_approver', '治理审批员')
ON DUPLICATE KEY UPDATE role_name = VALUES(role_name);

INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT r.id, p.permission_code
FROM iam_roles r
JOIN (SELECT 'analytics.query' permission_code UNION ALL SELECT 'governance.table.manage' UNION ALL SELECT 'governance.table.approve') p
WHERE r.role_code = 'platform_admin';

INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT r.id, 'analytics.query' FROM iam_roles r WHERE r.role_code IN ('data_analyst', 'data_developer', 'business_user');

INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT r.id, 'governance.table.approve' FROM iam_roles r WHERE r.role_code = 'governance_approver';
