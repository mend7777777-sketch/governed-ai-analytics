"""Streamlit chat UI for the local AI analytics API."""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st


API_URL = os.getenv("ANALYTICS_API_URL", "http://127.0.0.1:8010")

st.set_page_config(page_title="AI 数据分析助手", page_icon="A", layout="wide")
st.title("AI 数据分析助手")
st.caption("自然语言问数 | 只读 SQL | LLM 不接收数据库查询结果")

if "history" not in st.session_state:
    st.session_state.history = []


def run_question(question: str) -> None:
    with st.spinner("正在检索业务知识并生成只读 SQL..."):
        try:
            response = requests.post(
                f"{API_URL}/api/query", json={"question": question}, timeout=90
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = "后端服务未启动或查询失败。请确认 FastAPI 正在运行。"
            if getattr(exc, "response", None) is not None:
                detail = exc.response.json().get("detail", detail)
            st.session_state.history.append({"question": question, "error": detail})
            return
    st.session_state.history.append({"question": question, "result": response.json()})


with st.sidebar:
    st.subheader("示例问题")
    examples = [
        "2025年12月哪个品类退款率最高？",
        "2025年3月有多少个黑卡用户下单？",
        "2025年每月GMV环比增长率",
        "2025年连续3个月下单的用户数",
    ]
    for index, example in enumerate(examples):
        if st.button(example, key=f"example_{index}", use_container_width=True):
            run_question(example)
    if st.button("清空当前会话", use_container_width=True):
        st.session_state.history = []
        st.rerun()


for item in st.session_state.history:
    with st.chat_message("user"):
        st.write(item["question"])
    with st.chat_message("assistant"):
        if "error" in item:
            st.error(item["error"])
            continue
        result = item["result"]
        dataframe = pd.DataFrame(result["rows"], columns=result["columns"])
        if result["chart_type"] == "metric" and not dataframe.empty:
            st.metric(result["columns"][0], dataframe.iloc[0, 0])
        elif result["chart_type"] == "line" and len(result["columns"]) >= 2:
            st.line_chart(dataframe.set_index(result["columns"][0]))
        elif result["chart_type"] == "bar" and len(result["columns"]) >= 2:
            st.bar_chart(dataframe.set_index(result["columns"][0]))
        st.dataframe(dataframe, use_container_width=True, hide_index=True)
        with st.expander("查看生成 SQL"):
            st.code(result["sql"], language="sql")
        st.caption(
            f"返回 {result['row_count']} 行，耗时 {result['elapsed_ms']} ms；"
            "LLM 未接收数据库查询结果。"
        )

if question := st.chat_input("例如：2025年12月哪个品类退款率最高？"):
    run_question(question)
    st.rerun()
