# MySQL mock data generator

This script creates an e-commerce star schema in MySQL 8 and loads data for an AI analytics/Text2SQL project.

## Install

Create and activate a virtual environment, then install the two dependencies:

```powershell
pip install mysql-connector-python Faker
```

## Run

The script prompts for the password when `MYSQL_PASSWORD` is not set:

```powershell
python .\scripts\generate_mock_data.py --user root --database ai_analytics --reset
```

To create a larger dataset, for example 300,000 orders:

```powershell
python .\scripts\generate_mock_data.py --user root --database ai_analytics --orders 300000 --reset
```

Using an environment variable avoids placing a password in terminal history:

```powershell
$env:MYSQL_PASSWORD = "your-password"
python .\scripts\generate_mock_data.py --user root --database ai_analytics --reset
```

## Generated tables

- `dim_date`, `dim_region`, `dim_product`, `dim_user`: dimensions.
- `fact_orders`: order-level data with GMV and discounts.
- `fact_payments`: payment and refund data.

The generator uses the 2025 calendar and intentionally creates two analysis scenarios:

1. Lower East-China order volume and deeper discounts in November.
2. Higher refund probability for 3C digital products in December.

## First validation queries

```sql
SELECT d.month_num, r.region_name, ROUND(SUM(o.payable_amount), 2) AS gmv
FROM fact_orders o
JOIN dim_date d ON d.date_id = o.date_id
JOIN dim_region r ON r.region_id = o.region_id
GROUP BY d.month_num, r.region_name
ORDER BY d.month_num, r.region_name;

SELECT d.month_num, p.category_name,
       ROUND(SUM(pay.refund_amount) / NULLIF(SUM(pay.paid_amount), 0), 4) AS refund_rate
FROM fact_payments pay
JOIN fact_orders o ON o.order_id = pay.order_id
JOIN dim_date d ON d.date_id = pay.pay_date_id
JOIN dim_product p ON p.product_id = o.product_id
GROUP BY d.month_num, p.category_name
ORDER BY d.month_num, refund_rate DESC;
```
