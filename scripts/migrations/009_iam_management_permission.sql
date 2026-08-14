INSERT IGNORE INTO iam_role_permissions (role_id, permission_code)
SELECT id, 'iam.user.manage' FROM iam_roles WHERE role_code='platform_admin';
