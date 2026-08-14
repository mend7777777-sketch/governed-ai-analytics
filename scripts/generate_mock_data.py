"""Generate an e-commerce analytics dataset in MySQL 8.

The script creates a small star schema, then loads deterministic mock data for
Text2SQL and AI analytics demos. It deliberately includes two explainable
business events: a GMV decline in East China during November and a higher
refund rate for 3C products during December.
"""

from __future__ import annotations

import argparse
import getpass
import os
import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import mysql.connector
from faker import Faker


REGIONS = [
    ("华东", "上海"),
    ("华东", "浙江"),
    ("华东", "江苏"),
    ("华南", "广东"),
    ("华南", "福建"),
    ("华北", "北京"),
    ("华北", "河北"),
    ("西南", "四川"),
    ("西南", "重庆"),
]

CATEGORIES = {
    "3C数码": ("手机", "电脑", "耳机"),
    "家居生活": ("厨具", "收纳", "清洁"),
    "服饰鞋包": ("女装", "男装", "运动鞋"),
    "食品饮料": ("零食", "饮料", "生鲜"),
    "美妆个护": ("护肤", "彩妆", "洗护"),
}

CHANNELS = ["自然搜索", "短视频", "直播", "社交投放", "老客复购"]
ORDER_STATUSES = ["PAID", "REFUNDED"]


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load mock e-commerce data into MySQL 8")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "ai_analytics"))
    parser.add_argument("--orders", type=int, default=100_000, help="Number of orders to generate")
    parser.add_argument("--users", type=int, default=10_000)
    parser.add_argument("--products", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all demo tables")
    return parser.parse_args()


def connect(args: argparse.Namespace, database: str | None = None):
    return mysql.connector.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=database,
        autocommit=False,
    )


def create_schema(connection, reset: bool) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS dim_date (
            date_id INT PRIMARY KEY,
            full_date DATE NOT NULL UNIQUE,
            year_num SMALLINT NOT NULL,
            month_num TINYINT NOT NULL,
            month_name VARCHAR(12) NOT NULL,
            week_num TINYINT NOT NULL,
            day_of_month TINYINT NOT NULL,
            is_weekend TINYINT(1) NOT NULL
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_region (
            region_id INT PRIMARY KEY AUTO_INCREMENT,
            region_name VARCHAR(20) NOT NULL,
            province_name VARCHAR(20) NOT NULL,
            UNIQUE KEY uk_region_province (region_name, province_name)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_product (
            product_id INT PRIMARY KEY AUTO_INCREMENT,
            product_name VARCHAR(100) NOT NULL,
            category_name VARCHAR(30) NOT NULL,
            subcategory_name VARCHAR(30) NOT NULL,
            list_price DECIMAL(12,2) NOT NULL,
            INDEX idx_product_category (category_name, subcategory_name)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_user (
            user_id INT PRIMARY KEY AUTO_INCREMENT,
            user_name VARCHAR(50) NOT NULL,
            user_level VARCHAR(20) NOT NULL,
            register_channel VARCHAR(30) NOT NULL,
            register_date DATE NOT NULL,
            INDEX idx_user_channel (register_channel)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_orders (
            order_id BIGINT PRIMARY KEY,
            date_id INT NOT NULL,
            user_id INT NOT NULL,
            product_id INT NOT NULL,
            region_id INT NOT NULL,
            sales_channel VARCHAR(30) NOT NULL,
            quantity INT NOT NULL,
            order_amount DECIMAL(12,2) NOT NULL,
            discount_amount DECIMAL(12,2) NOT NULL,
            payable_amount DECIMAL(12,2) NOT NULL,
            order_status VARCHAR(20) NOT NULL,
            created_at DATETIME NOT NULL,
            INDEX idx_orders_date_region (date_id, region_id),
            INDEX idx_orders_product (product_id),
            CONSTRAINT fk_orders_date FOREIGN KEY (date_id) REFERENCES dim_date(date_id),
            CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES dim_user(user_id),
            CONSTRAINT fk_orders_product FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
            CONSTRAINT fk_orders_region FOREIGN KEY (region_id) REFERENCES dim_region(region_id)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_payments (
            payment_id BIGINT PRIMARY KEY,
            order_id BIGINT NOT NULL,
            pay_date_id INT NOT NULL,
            payment_method VARCHAR(20) NOT NULL,
            paid_amount DECIMAL(12,2) NOT NULL,
            refund_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
            payment_status VARCHAR(20) NOT NULL,
            paid_at DATETIME NOT NULL,
            INDEX idx_payments_date (pay_date_id),
            INDEX idx_payments_order (order_id),
            CONSTRAINT fk_payments_order FOREIGN KEY (order_id) REFERENCES fact_orders(order_id),
            CONSTRAINT fk_payments_date FOREIGN KEY (pay_date_id) REFERENCES dim_date(date_id)
        ) ENGINE=InnoDB
        """,
    ]
    cursor = connection.cursor()
    if reset:
        for table in ["fact_payments", "fact_orders", "dim_user", "dim_product", "dim_region", "dim_date"]:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
    for statement in statements:
        cursor.execute(statement)
    connection.commit()
    cursor.close()


def load_dimensions(connection, args: argparse.Namespace, rng: random.Random, fake: Faker) -> dict:
    cursor = connection.cursor()
    start = date(2025, 1, 1)
    end = date(2025, 12, 31)
    dates = []
    current = start
    while current <= end:
        dates.append((
            int(current.strftime("%Y%m%d")), current, current.year, current.month,
            current.strftime("%B"), current.isocalendar().week, current.day,
            int(current.weekday() >= 5),
        ))
        current += timedelta(days=1)
    cursor.executemany(
        "INSERT INTO dim_date VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE full_date=VALUES(full_date)",
        dates,
    )
    cursor.executemany(
        "INSERT INTO dim_region (region_name, province_name) VALUES (%s,%s) ON DUPLICATE KEY UPDATE region_name=VALUES(region_name)",
        REGIONS,
    )

    products = []
    for index in range(args.products):
        category = rng.choice(list(CATEGORIES))
        subcategory = rng.choice(CATEGORIES[category])
        base_price = rng.uniform(30, 6000) if category == "3C数码" else rng.uniform(20, 800)
        products.append((f"{category}-{subcategory}-{index + 1:04d}", category, subcategory, money(base_price)))
    cursor.executemany(
        "INSERT INTO dim_product (product_name, category_name, subcategory_name, list_price) VALUES (%s,%s,%s,%s)",
        products,
    )

    users = []
    for _ in range(args.users):
        register_date = start - timedelta(days=rng.randint(1, 730))
        users.append((fake.name(), rng.choices(["普通", "银卡", "金卡", "黑金"], [60, 25, 12, 3])[0], rng.choice(CHANNELS), register_date))
    cursor.executemany(
        "INSERT INTO dim_user (user_name, user_level, register_channel, register_date) VALUES (%s,%s,%s,%s)",
        users,
    )
    connection.commit()

    cursor.execute("SELECT product_id, category_name, list_price FROM dim_product ORDER BY product_id")
    products_by_id = cursor.fetchall()
    cursor.execute("SELECT region_id, region_name FROM dim_region ORDER BY region_id")
    regions_by_id = cursor.fetchall()
    cursor.close()
    return {"start": start, "products": products_by_id, "regions": regions_by_id}


def order_day(rng: random.Random, start: date) -> date:
    # November East-China GMV decline is caused by lower order volume, not a fake SQL result.
    candidate = start + timedelta(days=rng.randrange(365))
    if candidate.month == 11 and rng.random() < 0.25:
        candidate = start + timedelta(days=rng.randrange(304))
    return candidate


def load_facts(connection, args: argparse.Namespace, rng: random.Random, dimension_data: dict) -> None:
    cursor = connection.cursor()
    order_sql = """
        INSERT INTO fact_orders
        (order_id, date_id, user_id, product_id, region_id, sales_channel, quantity,
         order_amount, discount_amount, payable_amount, order_status, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    payment_sql = """
        INSERT INTO fact_payments
        (payment_id, order_id, pay_date_id, payment_method, paid_amount, refund_amount, payment_status, paid_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """
    orders, payments = [], []
    products, regions = dimension_data["products"], dimension_data["regions"]
    start = dimension_data["start"]

    for order_id in range(1, args.orders + 1):
        order_date = order_day(rng, start)
        product_id, category, price = rng.choice(products)
        region_id, region_name = rng.choice(regions)
        quantity = rng.choices([1, 2, 3], [75, 20, 5])[0]
        raw_amount = money(float(price) * quantity)
        discount_rate = rng.choice([0, 0, 0.05, 0.10, 0.15])
        discount = money(float(raw_amount) * discount_rate)
        # Lower demand and slightly deeper promotions make the November East decline explainable.
        if region_name == "华东" and order_date.month == 11:
            discount = money(float(raw_amount) * max(discount_rate, 0.12))
        payable = raw_amount - discount
        refund_probability = 0.035
        if category == "3C数码" and order_date.month == 12:
            refund_probability = 0.18
        status = "REFUNDED" if rng.random() < refund_probability else "PAID"
        created_at = f"{order_date.isoformat()} {rng.randrange(8, 23):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}"
        date_id = int(order_date.strftime("%Y%m%d"))
        orders.append((
            order_id, date_id, rng.randint(1, args.users), product_id, region_id, rng.choice(CHANNELS), quantity,
            raw_amount, discount, payable, status, created_at,
        ))
        refund = payable if status == "REFUNDED" else Decimal("0.00")
        payments.append((
            order_id, order_id, date_id, rng.choice(["微信支付", "支付宝", "银行卡"]), payable,
            refund, status, created_at,
        ))
        if len(orders) >= args.batch_size:
            cursor.executemany(order_sql, orders)
            cursor.executemany(payment_sql, payments)
            connection.commit()
            print(f"Loaded {order_id:,}/{args.orders:,} orders")
            orders.clear()
            payments.clear()
    if orders:
        cursor.executemany(order_sql, orders)
        cursor.executemany(payment_sql, payments)
        connection.commit()
    cursor.close()


def print_summary(connection) -> None:
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*), ROUND(SUM(payable_amount), 2) FROM fact_orders")
    count, gmv = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM fact_payments WHERE payment_status = 'REFUNDED'")
    refunds = cursor.fetchone()[0]
    cursor.close()
    print(f"Done. Orders: {count:,}; payable GMV: {gmv:,}; refunded orders: {refunds:,}")


def main() -> None:
    args = parse_args()
    if not args.password:
        args.password = getpass.getpass(f"MySQL password for {args.user}: ")
    if args.orders < 1 or args.users < 1 or args.products < 1:
        raise ValueError("--orders, --users and --products must all be positive")
    rng = random.Random(args.seed)
    fake = Faker("zh_CN")
    Faker.seed(args.seed)

    admin_connection = connect(args)
    admin_cursor = admin_connection.cursor()
    admin_cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{args.database}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
    )
    admin_connection.commit()
    admin_cursor.close()
    admin_connection.close()

    connection = connect(args, args.database)
    try:
        create_schema(connection, args.reset)
        dimension_data = load_dimensions(connection, args, rng, fake)
        load_facts(connection, args, rng, dimension_data)
        print_summary(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
