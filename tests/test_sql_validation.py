import pytest

from app.services.text2sql import QueryValidationError, validate_read_only_sql


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
    ],
)
def test_rejects_unsafe_or_unapproved_sql(sql):
    with pytest.raises(QueryValidationError):
        validate_read_only_sql(sql, ALLOWED_TABLES)
