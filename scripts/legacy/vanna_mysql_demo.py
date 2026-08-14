"""Vanna + MySQL demo for the ai_analytics mock warehouse.

Usage:
  1. Copy .env.example to .env and fill in connection/model settings.
  2. python vanna_mysql_demo.py --train
  3. python vanna_mysql_demo.py --question "2025年11月华东GMV是多少？"

Training is persisted under ./storage/chroma_ai_analytics. Do not delete that directory
unless you want to reset Vanna's learned DDL, metric definitions and SQL examples.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
# Vanna 2 keeps the v1-style Text2SQL adapters under the compatibility namespace.
from vanna.legacy.chromadb import ChromaDB_VectorStore
from vanna.legacy.openai import OpenAI_Chat


# Vanna logs full model responses; UTF-8 prevents Windows GBK console failures.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class AnalyticsVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self) -> None:
        config = {
            "api_key": required_env("OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "path": str((BASE_DIR.parent.parent / "storage" / "chroma_ai_analytics").resolve()),
        }
        ChromaDB_VectorStore.__init__(self, config=config)
        base_url = os.getenv("OPENAI_BASE_URL")
        client = OpenAI(api_key=config["api_key"], base_url=base_url) if base_url else OpenAI(api_key=config["api_key"])
        OpenAI_Chat.__init__(self, client=client, config=config)

    def submit_prompt(self, prompt, **kwargs) -> str:
        """Support both standard OpenAI SDK objects and string-returning compatible APIs."""
        model = kwargs.get("model") or self.config.get("model")
        response = self.client.chat.completions.create(
            model=model,
            messages=prompt,
            stop=None,
            temperature=self.temperature,
        )
        if isinstance(response, str):
            return response
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError(f"Unexpected model response type: {type(response).__name__}")
        return choices[0].message.content or ""


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Copy .env.example to .env and set it.")
    return value


def connect_mysql(vn: AnalyticsVanna) -> None:
    vn.connect_to_mysql(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        dbname=os.getenv("MYSQL_DATABASE", "ai_analytics"),
        user=required_env("MYSQL_USER"),
        password=required_env("MYSQL_PASSWORD"),
        # Local MySQL demo: avoid PyMySQL reading malformed Windows certificate-store entries.
        ssl_disabled=True,
    )


def train(vn: AnalyticsVanna) -> None:
    # Vanna retrieves this schema before it generates SQL.
    vn.train(ddl="""
CREATE TABLE dim_date (
  date_id INT PRIMARY KEY, full_date DATE, year_num SMALLINT, month_num TINYINT,
  month_name VARCHAR(12), week_num TINYINT, day_of_month TINYINT, is_weekend BOOLEAN
);
CREATE TABLE dim_region (
  region_id INT PRIMARY KEY, region_name VARCHAR(20), province_name VARCHAR(20)
);
CREATE TABLE dim_product (
  product_id INT PRIMARY KEY, product_name VARCHAR(100), category_name VARCHAR(30),
  subcategory_name VARCHAR(30), list_price DECIMAL(12,2)
);
CREATE TABLE dim_user (
  user_id INT PRIMARY KEY, user_name VARCHAR(50), user_level VARCHAR(20),
  register_channel VARCHAR(30), register_date DATE
);
CREATE TABLE fact_orders (
  order_id BIGINT PRIMARY KEY, date_id INT, user_id INT, product_id INT, region_id INT,
  sales_channel VARCHAR(30), quantity INT, order_amount DECIMAL(12,2),
  discount_amount DECIMAL(12,2), payable_amount DECIMAL(12,2),
  order_status VARCHAR(20), created_at DATETIME
);
CREATE TABLE fact_payments (
  payment_id BIGINT PRIMARY KEY, order_id BIGINT, pay_date_id INT,
  payment_method VARCHAR(20), paid_amount DECIMAL(12,2), refund_amount DECIMAL(12,2),
  payment_status VARCHAR(20), paid_at DATETIME
);
""")

    vn.train(documentation="""
事实表关联：fact_orders 是订单事实表，通过 date_id、user_id、product_id、region_id 分别关联
dim_date、dim_user、dim_product、dim_region。fact_payments 是支付事实表，通过 order_id 关联
fact_orders，通过 pay_date_id 关联 dim_date。订单类指标优先从 fact_orders 计算；退款和实收类
指标从 fact_payments 计算后再关联订单维度。
业务口径：GMV 指 fact_orders.payable_amount 的总和，包含已支付及已退款订单的应付金额。
订单金额指 order_amount，优惠金额指 discount_amount，应付金额指 payable_amount。订单数指
fact_orders 的订单行数。退款金额指 fact_payments.refund_amount 的总和。退款率 =
SUM(refund_amount) / SUM(paid_amount)，分母为 0 时使用 NULLIF 防止除零。客单价 =
SUM(payable_amount) / COUNT(*)，不要将客单价错误地除以用户数。
用户等级字段为 dim_user.user_level，合法取值仅为：普通、银卡、金卡、黑金。
业务别名中“黑卡用户”等价于 user_level = '黑金'，不要生成 user_level = '黑卡'。
“多少个用户下单”统计去重下单用户数，即 COUNT(DISTINCT fact_orders.user_id)；
“订单数”统计订单行数，即 COUNT(*)。
日期筛选应通过事实表日期键关联 dim_date.full_date；date_id 的格式是 YYYYMMDD。按月统计时，
必须同时使用 dim_date.year_num 和 month_num，或使用 full_date 月份范围，避免不同年份同月混在一起。
“环比”表示本月与上一个自然月比较；“同比”表示本月与上年同月比较。增长率公式为
(本期 - 对比期) / NULLIF(对比期, 0)。
连续 N 个月下单：先按用户和自然月去重，再用月份序号（year_num * 12 + month_num）判断连续性；
用户同月多笔订单只能算一个下单月份。
区域使用 dim_region.region_name，合法区域为华东、华南、华北、西南；省份使用 province_name。
商品品类使用 dim_product.category_name，合法品类为3C数码、家居生活、服饰鞋包、食品饮料、美妆个护。
渠道使用 fact_orders.sales_channel，合法值为自然搜索、短视频、直播、社交投放、老客复购。
订单状态使用 fact_orders.order_status，合法值为 PAID、REFUNDED；退款订单并不等于没有订单。
支付状态使用 fact_payments.payment_status，合法值为 PAID、REFUNDED。
不要虚构不存在的列、表、字段值或业务口径。所有查询只能使用 SELECT，默认返回聚合结果或最多 200 行明细。
""")

    examples = [
        (
            "2025年11月华东各省GMV是多少？",
            """SELECT r.province_name, ROUND(SUM(o.payable_amount), 2) AS gmv
FROM fact_orders o
JOIN dim_date d ON d.date_id = o.date_id
JOIN dim_region r ON r.region_id = o.region_id
WHERE d.full_date >= '2025-11-01' AND d.full_date < '2025-12-01'
  AND r.region_name = '华东'
GROUP BY r.province_name ORDER BY gmv DESC""",
        ),
        (
            "按月统计各区域GMV",
            """SELECT d.month_num, r.region_name, ROUND(SUM(o.payable_amount), 2) AS gmv
FROM fact_orders o
JOIN dim_date d ON d.date_id = o.date_id
JOIN dim_region r ON r.region_id = o.region_id
GROUP BY d.month_num, r.region_name
ORDER BY d.month_num, r.region_name""",
        ),
        (
            "2025年12月各品类退款率",
            """SELECT p.category_name,
       ROUND(SUM(pay.refund_amount) / NULLIF(SUM(pay.paid_amount), 0) * 100, 2) AS refund_rate_pct
FROM fact_payments pay
JOIN fact_orders o ON o.order_id = pay.order_id
JOIN dim_date d ON d.date_id = pay.pay_date_id
JOIN dim_product p ON p.product_id = o.product_id
WHERE d.full_date >= '2025-12-01' AND d.full_date < '2026-01-01'
GROUP BY p.category_name ORDER BY refund_rate_pct DESC""",
        ),
        (
            "各渠道的订单数和客单价",
            """SELECT o.sales_channel, COUNT(*) AS order_count,
       ROUND(SUM(o.payable_amount) / COUNT(*), 2) AS avg_order_value
FROM fact_orders o
GROUP BY o.sales_channel ORDER BY order_count DESC""",
        ),
        (
            "2025年3月有多少个黑卡用户下单？",
            """SELECT COUNT(DISTINCT o.user_id) AS user_count
FROM fact_orders o
JOIN dim_date d ON d.date_id = o.date_id
JOIN dim_user u ON u.user_id = o.user_id
WHERE d.full_date >= '2025-03-01' AND d.full_date < '2025-04-01'
  AND u.user_level = '黑金'""",
        ),
        (
            "2025年每月GMV环比增长率",
            """WITH monthly_gmv AS (
    SELECT d.year_num, d.month_num, SUM(o.payable_amount) AS gmv
    FROM fact_orders o
    JOIN dim_date d ON d.date_id = o.date_id
    WHERE d.year_num = 2025
    GROUP BY d.year_num, d.month_num
)
SELECT year_num, month_num, ROUND(gmv, 2) AS gmv,
       ROUND((gmv - LAG(gmv) OVER (ORDER BY year_num, month_num)) /
             NULLIF(LAG(gmv) OVER (ORDER BY year_num, month_num), 0) * 100, 2) AS mom_growth_pct
FROM monthly_gmv
ORDER BY year_num, month_num""",
        ),
        (
            "2025年连续3个月下单的用户数",
            """WITH monthly_users AS (
    SELECT DISTINCT o.user_id, d.year_num * 12 + d.month_num AS month_index
    FROM fact_orders o
    JOIN dim_date d ON d.date_id = o.date_id
    WHERE d.year_num = 2025
), consecutive_users AS (
    SELECT DISTINCT m1.user_id
    FROM monthly_users m1
    JOIN monthly_users m2 ON m2.user_id = m1.user_id
                         AND m2.month_index = m1.month_index + 1
    JOIN monthly_users m3 ON m3.user_id = m1.user_id
                         AND m3.month_index = m1.month_index + 2
)
SELECT COUNT(*) AS user_count FROM consecutive_users""",
        ),
    ]
    for question, sql in examples:
        vn.train(question=question, sql=sql)
    print("Training finished. Chroma data saved in storage/chroma_ai_analytics.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true", help="Train Vanna with DDL, metrics and SQL examples")
    parser.add_argument("--question", help="A Chinese analytics question")
    parser.add_argument(
        "--allow-llm-to-see-data",
        action="store_true",
        help="Allow Vanna to send intermediate query results to the LLM; use only with non-sensitive demo data",
    )
    args = parser.parse_args()
    if not args.train and not args.question:
        parser.error("Pass --train or --question")

    vn = AnalyticsVanna()
    connect_mysql(vn)
    if args.train:
        train(vn)
    if args.question:
        sql = vn.generate_sql(
            question=args.question,
            allow_llm_to_see_data=args.allow_llm_to_see_data,
        )
        print("\n--- Generated SQL ---\n" + sql)
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise RuntimeError(
                "Vanna did not return executable read-only SQL. "
                "For local mock data, retry with --allow-llm-to-see-data if the model requires an intermediate query."
            )
        result = vn.run_sql(sql)
        print("\n--- Query Result ---")
        print(result.to_string(index=False))


if __name__ == "__main__":
    main()
