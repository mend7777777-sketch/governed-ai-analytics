"""Operational entry point for loading governed Text2SQL knowledge."""

from app.integrations.vanna_client import AnalyticsVanna, connect_mysql
from scripts.legacy.vanna_mysql_demo import train


def main() -> None:
    vn = AnalyticsVanna()
    connect_mysql(vn)
    train(vn)


if __name__ == "__main__":
    main()
