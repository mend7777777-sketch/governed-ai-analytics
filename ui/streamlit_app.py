"""Streamlit chat UI for the local AI analytics API."""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st


API_URL = os.getenv("ANALYTICS_API_URL", "http://127.0.0.1:8010")

st.set_page_config(page_title="AI 数据分析助手", page_icon="A", layout="wide")

if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None
if "history" not in st.session_state:
    st.session_state.history = []

def api_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def governance_post(path: str, payload: dict) -> None:
    try:
        response = requests.post(f"{API_URL}{path}", json=payload, headers=api_headers(), timeout=20)
        response.raise_for_status()
        st.success(response.json().get("approval_status", "操作成功"))
        st.rerun()
    except requests.RequestException as exc:
        detail = "治理操作失败。"
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
        st.error(detail)


def iam_post(path: str, payload: dict) -> None:
    try:
        response = requests.post(f"{API_URL}{path}", json=payload, headers=api_headers(), timeout=20)
        response.raise_for_status()
        st.success("操作成功。")
        st.rerun()
    except requests.RequestException as exc:
        detail = "系统管理操作失败。"
        if getattr(exc, "response", None) is not None:
            try:
                detail = exc.response.json().get("detail", detail)
            except ValueError:
                pass
        st.error(detail)

if not st.session_state.access_token:
    st.title("AI 数据分析助手")
    st.caption("请登录后使用智能问数和数据治理功能")
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")
    if submitted:
        try:
            response = requests.post(f"{API_URL}/api/auth/login", json={"username": username, "password": password}, timeout=20)
            response.raise_for_status()
            data = response.json()
            st.session_state.access_token = data["access_token"]
            st.session_state.refresh_token = data.get("refresh_token")
            st.session_state.username = data.get("username", username)
            st.session_state.roles = data.get("roles", [])
            st.rerun()
        except requests.RequestException:
            st.error("用户名或密码错误，或后端服务不可用。")
    st.stop()

with st.sidebar:
    page = st.radio("功能", ["智能问数", "数据治理", "知识库", "系统管理"], index=0)
    st.caption(f"当前用户：{st.session_state.get('username', '')}")
    if st.button("退出登录"):
        if st.session_state.refresh_token:
            try:
                requests.post(f"{API_URL}/api/auth/logout", json={"refresh_token": st.session_state.refresh_token}, timeout=10)
            except requests.RequestException:
                pass
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.history = []
        st.rerun()
if page == "系统管理":
    st.title("系统管理")
    if "platform_admin" not in st.session_state.get("roles", []):
        st.warning("只有平台管理员可以管理用户和组织。")
        st.stop()
    try:
        departments = requests.get(f"{API_URL}/api/iam/departments", headers=api_headers(), timeout=15).json().get("departments", [])
        positions = requests.get(f"{API_URL}/api/iam/positions", headers=api_headers(), timeout=15).json().get("positions", [])
        roles = requests.get(f"{API_URL}/api/iam/roles", headers=api_headers(), timeout=15).json().get("roles", [])
        users_response = requests.get(f"{API_URL}/api/iam/users", headers=api_headers(), timeout=15)
        users_response.raise_for_status()
        users = users_response.json().get("users", [])
    except requests.RequestException:
        st.error("IAM 接口不可用，请确认已执行 009 迁移并重启 FastAPI。")
        st.stop()
    tabs = st.tabs(["用户", "部门", "岗位", "角色"])
    with tabs[0]:
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
        with st.form("create_user"):
            username = st.text_input("用户名")
            display_name = st.text_input("显示名称")
            password = st.text_input("初始密码", type="password")
            department = st.selectbox("部门", [""] + [item["department_code"] for item in departments], format_func=lambda value: "未设置" if not value else value)
            position = st.selectbox("岗位", [""] + [item["position_code"] for item in positions], format_func=lambda value: "未设置" if not value else value)
            selected_roles = st.multiselect("角色", [item["role_code"] for item in roles])
            if st.form_submit_button("创建用户", type="primary"):
                iam_post("/api/iam/users", {"username": username, "display_name": display_name, "password": password, "department_code": department or None, "position_code": position or None, "roles": selected_roles})
        if users:
            selected_user = st.selectbox("选择用户修改状态", [item["username"] for item in users])
            status = st.selectbox("账号状态", ["ACTIVE", "LOCKED", "DISABLED"])
            if st.button("更新账号状态"):
                iam_post(f"/api/iam/users/{selected_user}/status", {"status": status})
    with tabs[1]:
        st.dataframe(pd.DataFrame(departments), use_container_width=True, hide_index=True)
        with st.form("create_department"):
            code = st.text_input("部门编码")
            name = st.text_input("部门名称")
            if st.form_submit_button("新增部门"):
                iam_post("/api/iam/departments", {"code": code, "name": name})
    with tabs[2]:
        st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)
        with st.form("create_position"):
            code = st.text_input("岗位编码")
            name = st.text_input("岗位名称")
            if st.form_submit_button("新增岗位"):
                iam_post("/api/iam/positions", {"code": code, "name": name})
    with tabs[3]:
        st.dataframe(pd.DataFrame(roles), use_container_width=True, hide_index=True)
    st.stop()

if page == "知识库":
    st.title("知识库管理")
    if "platform_admin" not in st.session_state.get("roles", []):
        st.warning("只有平台管理员可以维护知识库。")
        st.stop()
    st.caption("提交业务定义、指标口径和 SQL 示例，训练到当前 Vanna/Chroma 向量库。")
    with st.form("knowledge_document"):
        title = st.text_input("文档标题")
        document_type = st.selectbox("文档类型", ["business_definition", "metric_definition", "sql_example", "table_description"])
        content = st.text_area("文档内容", height=240, placeholder="例如：GMV 指已支付订单的 payable_amount 之和，不包含退款。")
        if st.form_submit_button("提交并训练", type="primary"):
            if not title.strip() or not content.strip():
                st.error("标题和内容不能为空。")
            else:
                try:
                    response = requests.post(f"{API_URL}/api/knowledge/documents", headers=api_headers(), json={"title": title, "document_type": document_type, "content": content}, timeout=120)
                    response.raise_for_status()
                    st.success("知识已训练到向量库。")
                    st.rerun()
                except requests.RequestException as exc:
                    detail = "知识训练失败。"
                    if getattr(exc, "response", None) is not None:
                        try:
                            detail = exc.response.json().get("detail", detail)
                        except ValueError:
                            pass
                    st.error(detail)
    try:
        response = requests.get(f"{API_URL}/api/knowledge/documents", headers=api_headers(), timeout=15)
        response.raise_for_status()
        documents = response.json().get("documents", [])
        st.dataframe(pd.DataFrame(documents), use_container_width=True, hide_index=True)
    except requests.RequestException:
        st.error("知识库元数据接口不可用，请确认已执行 008 迁移。")
    st.stop()

if page == "数据治理":
    st.title("数据治理")
    st.caption("已发布表由治理元数据动态控制，新增表无需修改代码白名单。")
    try:
        response = requests.get(f"{API_URL}/api/governance/tables", headers=api_headers(), timeout=15)
        response.raise_for_status()
        tables = response.json().get("tables", [])
        if tables:
            st.dataframe(pd.DataFrame(tables), use_container_width=True, hide_index=True)
            if "platform_admin" in st.session_state.get("roles", []):
                st.subheader("治理审批")
                st.caption("管理员操作会写入审计日志；撤销会禁用该表的 AI 查询。")
                for table in tables:
                    table_name = table["table_name"]
                    st.markdown(f"**{table_name}** · {table.get('approval_status', '')}")
                    reason = st.text_input("备注", key=f"reason_{table_name}")
                    cols = st.columns(4)
                    for column, action, label in zip(cols, ["submit", "approve", "reject", "revoke"], ["提交", "通过", "驳回", "撤销"]):
                        if column.button(label, key=f"{action}_{table_name}"):
                            governance_post(f"/api/governance/tables/{table_name}/{action}", {"reason": reason})
                st.divider()
                st.subheader("登记新表")
                with st.form("register_table"):
                    table_name = st.text_input("表名")
                    business_name = st.text_input("业务名称")
                    owner_name = st.text_input("负责人")
                    sensitivity = st.selectbox("敏感级别", ["PUBLIC", "INTERNAL", "SENSITIVE"])
                    if st.form_submit_button("登记"):
                        if not table_name or not business_name or not owner_name:
                            st.error("表名、业务名称和负责人不能为空。")
                        else:
                            governance_post("/api/governance/tables", {"table_name": table_name, "business_name": business_name, "owner_name": owner_name, "sensitivity_level": sensitivity})
        else:
            st.info("当前没有已登记的治理表。")
    except requests.RequestException:
        st.error("治理元数据接口不可用，请先启动 FastAPI 后端。")
    st.stop()

st.title("AI 数据分析助手")
st.caption("自然语言问数 | 只读 SQL | LLM 不接收数据库查询结果")

def run_question(question: str) -> None:
    with st.spinner("正在检索业务知识并生成只读 SQL..."):
        try:
            response = requests.post(
                f"{API_URL}/api/query", json={"question": question}, headers=api_headers(), timeout=90
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
