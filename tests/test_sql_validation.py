import pytest

from app.services.text2sql import QueryValidationError, bound_read_only_sql, validate_read_only_sql


ALLOWED_TABLES = {"dim_date", "fact_orders"}


def test_allows_single_read_only_select():
    sql = "SELECT d.year_num, COUNT(*) AS order_count FROM fact_orders o JOIN dim_date d ON d.date_id=o.date_id"
    assert validate_read_only_sql(sql, ALLOWED_TABLES) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM fact_orders",
        "SELECT * FROM fact_orders; DROP TABLE dim_date",
        "SELECT * FROM fact_orders -- bypass policy",
        "SELECT * FROM mysql.user",
        "SELECT 1; SELECT 2",
        "SELECT SLEEP(10) FROM fact_orders",
        "SELECT * FROM fact_orders FOR UPDATE",
    ],
)
def test_rejects_unsafe_or_unapproved_sql(sql):
    with pytest.raises(QueryValidationError):
        validate_read_only_sql(sql, ALLOWED_TABLES)


def test_server_side_limit_is_added_for_unbounded_query():
    bounded = bound_read_only_sql("SELECT order_id FROM fact_orders", 200)
    assert "LIMIT 201" in bounded.upper()


def test_existing_small_limit_is_preserved():
    bounded = bound_read_only_sql("SELECT order_id FROM fact_orders LIMIT 20", 200)
    assert "LIMIT 20" in bounded.upper()
