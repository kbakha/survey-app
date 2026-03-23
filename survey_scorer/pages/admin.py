from pathlib import Path

import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import init_db, query_results
from reporter import export_detail, export_summary, export_group

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "survey.db"
RESULTS_DIR = BASE_DIR / "results"

st.set_page_config(page_title="Результаты", page_icon="📊", layout="wide")

# ── Password ──────────────────────────────────────────────────────────────────
PASSWORD = st.secrets.get("ADMIN_PASSWORD", "admin123")

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 Просмотр результатов")
    pwd = st.text_input("Пароль", type="password")
    if st.button("Войти", type="primary"):
        if pwd == PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Неверный пароль")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
def load_data(instrument_id=None, respondent_id=None):
    if not DB_PATH.exists():
        return []
    with init_db(DB_PATH) as conn:
        return query_results(conn, instrument_id=instrument_id, respondent_id=respondent_id)

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("📊 Результаты исследования")

rows = load_data()

if not rows:
    st.info("Пока нет данных. Участники ещё не прошли тесты.")
    st.stop()

df_all = pd.DataFrame(rows)

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Фильтры")

    instruments = ["Все"] + sorted(df_all["instrument_id"].unique().tolist())
    sel_instrument = st.selectbox("Методика", instruments)

    respondents = ["Все"] + sorted(df_all["respondent_id"].unique().tolist())
    sel_respondent = st.selectbox("Участник", respondents)

    st.divider()
    if st.button("Выйти"):
        st.session_state.auth = False
        st.rerun()

# Apply filters
filtered = rows
if sel_instrument != "Все":
    filtered = [r for r in filtered if r["instrument_id"] == sel_instrument]
if sel_respondent != "Все":
    filtered = [r for r in filtered if r["respondent_id"] == sel_respondent]

df = pd.DataFrame(filtered)

# ── Metrics ───────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.metric("Участников", df["respondent_id"].nunique())
col2.metric("Методик", df["instrument_id"].nunique())
col3.metric("Записей", len(df))

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Сводная таблица", "Детальные результаты", "Средние по группе"])

with tab1:
    st.subheader("Один ряд на участника — баллы по всем шкалам")
    df["column"] = df["instrument_id"] + "_" + df["scale_id"]
    pivot = df.pivot_table(
        index="respondent_id",
        columns="column",
        values="raw_score",
        aggfunc="first",
    ).reset_index()
    pivot.columns.name = None
    st.dataframe(pivot, use_container_width=True, hide_index=True)

    csv = pivot.to_csv(index=False, encoding="utf-8").encode("utf-8-sig")
    st.download_button("⬇ Скачать CSV", csv, "results_summary.csv", "text/csv")

with tab2:
    st.subheader("Детальные результаты с интерпретацией")
    detail_cols = ["respondent_id", "instrument_id", "scale_name", "raw_score", "label", "interpretation", "calculated_at"]
    df_detail = df[detail_cols].copy()
    df_detail.columns = ["Участник", "Методика", "Шкала", "Балл", "Уровень", "Интерпретация", "Дата"]

    # Highlight by level
    def highlight_level(row):
        colors = {"Высокий": "#d4edda", "Средний": "#fff3cd", "Низкий": "#f8d7da",
                  "Толерантность": "#d4edda", "Нейтральный": "#fff3cd", "Интолерантность": "#f8d7da"}
        color = colors.get(row["Уровень"], "")
        return [f"background-color: {color}" if color else ""] * len(row)

    st.dataframe(
        df_detail.style.apply(highlight_level, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    csv2 = df_detail.to_csv(index=False, encoding="utf-8").encode("utf-8-sig")
    st.download_button("⬇ Скачать CSV", csv2, "results_detail.csv", "text/csv")

with tab3:
    st.subheader("Средние, min, max, std по каждой шкале")
    df["column"] = df["instrument_id"] + "_" + df["scale_id"]
    group = (
        df.groupby(["instrument_id", "scale_id", "scale_name"])["raw_score"]
        .agg(n="count", mean="mean", min="min", max="max", std="std")
        .round(2)
        .reset_index()
    )
    group.columns = ["Методика", "Шкала (id)", "Шкала", "N", "Среднее", "Min", "Max", "Std"]
    st.dataframe(group, use_container_width=True, hide_index=True)

    csv3 = group.to_csv(index=False, encoding="utf-8").encode("utf-8-sig")
    st.download_button("⬇ Скачать CSV", csv3, "results_group.csv", "text/csv")
