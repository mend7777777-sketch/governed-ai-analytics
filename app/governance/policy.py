"""Runtime table authorization backed by governance metadata."""

from __future__ import annotations

import re


TABLE_PATTERN = re.compile(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z_][\w]*)`?", re.IGNORECASE)


class PolicyViolation(ValueError):
    pass


def referenced_tables(sql: str) -> set[str]:
    return {name.lower() for name in TABLE_PATTERN.findall(sql)}


def validate_authorized_tables(sql: str, published_tables: set[str]) -> None:
    denied = referenced_tables(sql) - published_tables
    if denied:
        raise PolicyViolation("表尚未发布到 AI 数据服务：" + ", ".join(sorted(denied)))
