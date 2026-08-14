"""Initialize the Compose MySQL database with mock data and bootstrap metadata."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import mysql.connector
from argon2 import PasswordHasher


ROOT = Path(__file__).resolve().parents[1]


def run_sql_file(connection, path: Path) -> None:
    sql = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    finally:
        cursor.close()


def main() -> None:
    env = os.environ.copy()
    subprocess.run(
        [
            sys.executable, "scripts/generate_mock_data.py", "--host", env["MYSQL_HOST"], "--port", env.get("MYSQL_PORT", "3306"),
            "--user", env["MYSQL_USER"], "--password", env["MYSQL_PASSWORD"], "--database", env["MYSQL_DATABASE"],
            "--orders", env.get("MOCK_ORDERS", "100000"), "--users", env.get("MOCK_USERS", "10000"),
            "--products", env.get("MOCK_PRODUCTS", "500"),
        ],
        cwd=ROOT,
        check=True,
    )
    connection = mysql.connector.connect(
        host=env["MYSQL_HOST"], port=int(env.get("MYSQL_PORT", "3306")), user=env["MYSQL_USER"],
        password=env["MYSQL_PASSWORD"], database=env["MYSQL_DATABASE"],
    )
    try:
        for file_name in ("01_governance_metadata.sql", "02_identity_and_auth.sql", "03_data_access.sql", "04_knowledge.sql"):
            run_sql_file(connection, ROOT / "scripts" / "bootstrap" / file_name)
        cursor = connection.cursor()
        try:
            username = env.get("INITIAL_ADMIN_USERNAME", "admin")
            password = env["INITIAL_ADMIN_PASSWORD"]
            display_name = env.get("INITIAL_ADMIN_DISPLAY_NAME", "平台管理员")
            cursor.execute(
                "INSERT IGNORE INTO iam_users (username, display_name, password_hash) VALUES (%s,%s,%s)",
                (username, display_name, PasswordHasher().hash(password)),
            )
            cursor.execute(
                "INSERT IGNORE INTO iam_user_roles (user_id, role_id) "
                "SELECT u.id, r.id FROM iam_users u JOIN iam_roles r ON r.role_code='platform_admin' "
                "WHERE u.username=%s",
                (username,),
            )
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
