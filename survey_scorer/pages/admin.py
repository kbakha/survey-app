from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import init_db, query_results, query_respondents, delete_respondent
from reporter import export_detail, export_summary, export_group

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "survey.db"

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

# ── Chart helpers ─────────────────────────────────────────────────────────────
LEVEL_COLORS = {
    "Высокий": "#4CAF50", "Средний": "#FFC107", "Низкий": "#F44336",
    "Ведущий": "#4CAF50",
    "Толерантность": "#4CAF50", "Нейтральный": "#FFC107", "Интолерантность": "#F44336",
}

def charts_ptr(df_all: pd.DataFrame):
    df = df_all[df_all["instrument_id"] == "ptr"].copy()
    if df.empty:
        st.info("Нет данных по ПТР")
        return

    # ── Общий индекс: распределение уровней ──────────────────────────────────
    total = df[df["scale_id"] == "total"].copy()
    if not total.empty:
        level_counts = total["label"].value_counts().reset_index()
        level_counts.columns = ["Уровень", "Количество"]
        level_counts["Процент"] = (level_counts["Количество"] / level_counts["Количество"].sum() * 100).round(1)
        level_counts["Метка"] = level_counts.apply(
            lambda r: f"{r['Количество']} чел. ({r['Процент']}%)", axis=1
        )
        order = ["Высокий", "Средний", "Низкий"]
        level_counts["Уровень"] = pd.Categorical(level_counts["Уровень"], categories=order, ordered=True)
        level_counts = level_counts.sort_values("Уровень")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Распределение уровней ПТР")
            fig = px.bar(
                level_counts, x="Уровень", y="Количество", text="Метка",
                color="Уровень",
                color_discrete_map=LEVEL_COLORS,
                labels={"Количество": "Количество участников"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False, yaxis_title="Количество участников")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Процентное соотношение уровней ПТР")
            fig2 = px.pie(
                level_counts, names="Уровень", values="Количество",
                color="Уровень",
                color_discrete_map=LEVEL_COLORS,
            )
            fig2.update_traces(textinfo="percent+label")
            st.plotly_chart(fig2, use_container_width=True)

    # ── Гистограмма с кривой Гаусса ───────────────────────────────────────
    if not total.empty and len(total) >= 3:
        st.subheader("Распределение баллов ПТР (гистограмма + кривая нормального распределения)")
        scores = total["raw_score"].values
        mu, sigma = scores.mean(), scores.std()

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=scores, nbinsx=12, histnorm="probability density",
            name="Распределение", marker_color="#5B9BD5", opacity=0.7,
        ))
        if sigma > 0:
            x_range = np.linspace(max(0, mu - 3 * sigma), mu + 3 * sigma, 100)
            y_gauss = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_range - mu) / sigma) ** 2)
            fig_hist.add_trace(go.Scatter(
                x=x_range, y=y_gauss, mode="lines",
                name=f"Норм. распр. (μ={mu:.1f}, σ={sigma:.1f})",
                line=dict(color="#F44336", width=2),
            ))
        fig_hist.update_layout(
            xaxis_title="Балл ПТР", yaxis_title="Плотность",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    # ── Box-plot ───────────────────────────────────────────────────────────
    if not total.empty:
        st.subheader("Ящик с усами (Box-plot) — баллы ПТР")
        fig_box = px.box(
            total, y="raw_score", points="all",
            labels={"raw_score": "Балл ПТР"},
            color_discrete_sequence=["#5B9BD5"],
        )
        fig_box.update_layout(showlegend=False)
        st.plotly_chart(fig_box, use_container_width=True)

    # ── Средние баллы по подшкалам ────────────────────────────────────────────
    st.subheader("Средние баллы по подшкалам ПТР")
    subscales = df[df["scale_id"] != "total"]
    if not subscales.empty:
        means = subscales.groupby("scale_name")["raw_score"].mean().round(2).reset_index()
        means.columns = ["Шкала", "Средний балл"]
        fig3 = px.bar(
            means, x="Средний балл", y="Шкала", orientation="h",
            text="Средний балл", color_discrete_sequence=["#5B9BD5"],
        )
        fig3.update_traces(textposition="outside")
        fig3.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig3, use_container_width=True)


def charts_mstat(df_all: pd.DataFrame):
    df_m = df_all[(df_all["instrument_id"] == "mstat1") & (df_all["scale_id"] == "T")].copy()
    if df_m.empty:
        st.info("Нет данных по MSTAT-1")
        return

    # ── Распределение уровней ─────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Распределение уровней MSTAT-1")
        counts = df_m["label"].value_counts().reset_index()
        counts.columns = ["Уровень", "Количество"]
        counts["Процент"] = (counts["Количество"] / counts["Количество"].sum() * 100).round(1)
        counts["Метка"] = counts.apply(lambda r: f"{r['Количество']} чел. ({r['Процент']}%)", axis=1)
        fig = px.bar(
            counts, x="Уровень", y="Количество", text="Метка",
            color="Уровень", color_discrete_map=LEVEL_COLORS,
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # ── Корреляция MSTAT-1 × ПТР ─────────────────────────────────────────────
    df_p = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
        ["respondent_id", "raw_score"]
    ].rename(columns={"raw_score": "ptr_total"})

    merged = df_m[["respondent_id", "raw_score"]].rename(columns={"raw_score": "mstat_T"}).merge(
        df_p, on="respondent_id", how="inner"
    )

    with col2:
        st.subheader("Корреляция MSTAT-1 и ПТР")
        if len(merged) < 2:
            st.info("Нужно минимум 2 участника с обоими тестами")
        else:
            merged["Уровень"] = merged["mstat_T"].apply(
                lambda t: "Толерантность" if t > 0 else ("Интолерантность" if t < 0 else "Нейтральный")
            )
            fig2 = px.scatter(
                merged, x="mstat_T", y="ptr_total", text="respondent_id",
                color="Уровень", color_discrete_map=LEVEL_COLORS,
                trendline="ols", trendline_scope="overall",
                labels={"mstat_T": "MSTAT-1 (Толерантность)", "ptr_total": "ПТР (Индекс)"},
            )
            fig2.update_traces(textposition="top center")
            fig2.add_vline(x=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig2, use_container_width=True)


def charts_usk(df_all: pd.DataFrame):
    df = df_all[df_all["instrument_id"] == "usk"].copy()
    if df.empty:
        st.info("Нет данных по УСК")
        return

    USK_SCALE_ORDER = [
        "Ио — Общая интернальность",
        "Ид — Достижения",
        "Ин — Неудачи",
        "Ис — Семейные отношения",
        "Ип — Производственные отношения",
        "Им — Межличностные отношения",
        "Из — Здоровье и болезнь",
    ]

    # ── Общая интернальность: распределение уровней ──────────────────────────
    total = df[df["scale_id"] == "io"].copy()
    if not total.empty:
        level_counts = total["label"].value_counts().reset_index()
        level_counts.columns = ["Уровень", "Количество"]
        level_counts["Процент"] = (level_counts["Количество"] / level_counts["Количество"].sum() * 100).round(1)
        level_counts["Метка"] = level_counts.apply(
            lambda r: f"{r['Количество']} чел. ({r['Процент']}%)", axis=1
        )
        order = ["Высокий", "Средний", "Низкий"]
        level_counts["Уровень"] = pd.Categorical(level_counts["Уровень"], categories=order, ordered=True)
        level_counts = level_counts.sort_values("Уровень")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Распределение уровней (Общая интернальность Ио)")
            fig = px.bar(
                level_counts, x="Уровень", y="Количество", text="Метка",
                color="Уровень",
                color_discrete_map=LEVEL_COLORS,
                labels={"Количество": "Количество участников"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False, yaxis_title="Количество участников")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Процентное соотношение уровней Ио")
            fig2 = px.pie(
                level_counts, names="Уровень", values="Количество",
                color="Уровень",
                color_discrete_map=LEVEL_COLORS,
            )
            fig2.update_traces(textinfo="percent+label")
            st.plotly_chart(fig2, use_container_width=True)

    # ── Средние баллы по всем шкалам: радарная диаграмма ────────────────────
    st.subheader("Профиль УСК — средние баллы по шкалам")
    subscales = df[df["scale_id"] != "io"].copy()
    if not subscales.empty:
        # Попробуем разбить на группы по ПТР
        df_ptr = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
            ["respondent_id", "label"]
        ].rename(columns={"label": "ptr_level"})
        df_radar = subscales.merge(df_ptr, on="respondent_id", how="left")
        df_radar["ptr_level"] = df_radar["ptr_level"].fillna("Все участники")

        groups = df_radar["ptr_level"].unique().tolist()
        fig3 = go.Figure()
        radar_scales = [s for s in USK_SCALE_ORDER if s != "Ио — Общая интернальность"]

        for group in groups:
            subset = df_radar[df_radar["ptr_level"] == group]
            means = subset.groupby("scale_name")["raw_score"].mean().reindex(radar_scales).round(2)
            fig3.add_trace(go.Scatterpolar(
                r=means.tolist() + [means.iloc[0]],
                theta=radar_scales + [radar_scales[0]],
                fill="toself",
                name=group,
            ))

        fig3.update_layout(
            polar=dict(radialaxis=dict(visible=True)),
            legend_title="Группа (уровень ПТР)",
        )
        st.plotly_chart(fig3, use_container_width=True)

    # ── Корреляция Ио × ПТР ──────────────────────────────────────────────────
    st.subheader("Корреляция УСК (Ио) и ПТР")
    df_io = df[df["scale_id"] == "io"][["respondent_id", "raw_score"]].rename(columns={"raw_score": "usk_io"})
    df_ptr2 = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
        ["respondent_id", "raw_score"]
    ].rename(columns={"raw_score": "ptr_total"})
    merged = df_io.merge(df_ptr2, on="respondent_id", how="inner")

    if len(merged) < 2:
        st.info("Нужно минимум 2 участника с обоими тестами")
    else:
        fig4 = px.scatter(
            merged, x="usk_io", y="ptr_total", text="respondent_id",
            trendline="ols",
            labels={"usk_io": "УСК Ио (Общая интернальность)", "ptr_total": "ПТР (Индекс)"},
            color_discrete_sequence=["#5B9BD5"],
        )
        fig4.update_traces(textposition="top center")
        fig4.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig4, use_container_width=True)

    # ── Столбчатая: средний ПТР по группам интернальности ─────────────────
    st.subheader("Средний балл ПТР по уровню интернальности (Ио)")
    if not total.empty:
        io_with_ptr = total[["respondent_id", "label"]].rename(columns={"label": "Ио_уровень"}).merge(
            df_ptr2, on="respondent_id", how="inner"
        )
        if not io_with_ptr.empty:
            group_means = io_with_ptr.groupby("Ио_уровень")["ptr_total"].mean().round(2).reset_index()
            group_means.columns = ["Группа", "Средний ПТР"]
            order = ["Низкий", "Средний", "Высокий"]
            group_means["Группа"] = pd.Categorical(group_means["Группа"], categories=order, ordered=True)
            group_means = group_means.sort_values("Группа")
            fig5 = px.bar(
                group_means, x="Группа", y="Средний ПТР", text="Средний ПТР",
                color="Группа", color_discrete_map=LEVEL_COLORS,
                labels={"Средний ПТР": "Средний балл ПТР"},
            )
            fig5.update_traces(textposition="outside")
            fig5.update_layout(showlegend=False)
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.info("Нужны данные по обоим тестам (УСК и ПТР)")


def charts_mis(df_all: pd.DataFrame):
    df = df_all[df_all["instrument_id"] == "mis"].copy()
    if df.empty:
        st.info("Нет данных по МИС")
        return

    MIS_SCALE_ORDER = [
        "Открытость", "Самоуверенность", "Саморуководство",
        "Отраженное самоотношение", "Самоценность", "Самопринятие",
        "Самопривязанность", "Внутренняя конфликтность", "Самообвинение",
    ]

    # ── Стековая гистограмма: распределение уровней по шкалам ─────────────
    st.subheader("Распределение уровней по шкалам МИС")
    level_order = ["Низкий", "Средний", "Высокий"]
    stacked = df.groupby(["scale_name", "label"]).size().reset_index(name="n")
    stacked["label"] = pd.Categorical(stacked["label"], categories=level_order, ordered=True)
    stacked["scale_name"] = pd.Categorical(stacked["scale_name"], categories=MIS_SCALE_ORDER, ordered=True)
    stacked = stacked.sort_values(["scale_name", "label"])
    total_per_scale = stacked.groupby("scale_name")["n"].transform("sum")
    stacked["pct"] = (stacked["n"] / total_per_scale * 100).round(1)

    fig = px.bar(
        stacked, x="pct", y="scale_name", color="label",
        orientation="h", barmode="stack",
        color_discrete_map=LEVEL_COLORS,
        labels={"pct": "% участников", "scale_name": "Шкала", "label": "Уровень"},
        text=stacked["pct"].apply(lambda x: f"{x}%" if x >= 8 else ""),
        category_orders={"label": level_order},
    )
    fig.update_layout(xaxis_range=[0, 100], legend_title="Уровень")
    st.plotly_chart(fig, use_container_width=True)

    # ── Радарная диаграмма: средние баллы по шкалам ───────────────────────
    st.subheader("Профиль самоотношения — средние баллы по группе")

    df_ptr = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
        ["respondent_id", "label"]
    ].rename(columns={"label": "ptr_level"})
    df_radar = df.merge(df_ptr, on="respondent_id", how="left")
    df_radar["ptr_level"] = df_radar["ptr_level"].fillna("Все участники")

    groups = df_radar["ptr_level"].unique().tolist()
    fig2 = go.Figure()

    for group in groups:
        subset = df_radar[df_radar["ptr_level"] == group]
        means = subset.groupby("scale_name")["raw_score"].mean().reindex(MIS_SCALE_ORDER).round(2)
        fig2.add_trace(go.Scatterpolar(
            r=means.tolist() + [means.iloc[0]],
            theta=MIS_SCALE_ORDER + [MIS_SCALE_ORDER[0]],
            fill="toself",
            name=group,
        ))

    fig2.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        legend_title="Группа (уровень ПТР)",
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Корреляционная тепловая карта: ПТР × шкалы МИС ───────────────────
    st.subheader("Корреляция шкал МИС с ПТР (тепловая карта)")
    df_ptr = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
        ["respondent_id", "raw_score"]
    ].rename(columns={"raw_score": "ПТР"})

    mis_wide = df.pivot_table(
        index="respondent_id", columns="scale_name", values="raw_score", aggfunc="first",
    ).reset_index()
    mis_corr = mis_wide.merge(df_ptr, on="respondent_id", how="inner")

    if len(mis_corr) >= 3:
        cols_for_corr = MIS_SCALE_ORDER + ["ПТР"]
        corr = mis_corr[cols_for_corr].corr().round(2)
        fig_hm = px.imshow(
            corr, text_auto=True, color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1, aspect="auto",
        )
        fig_hm.update_layout(xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_hm, use_container_width=True)
    else:
        st.info("Нужно минимум 3 участника с обоими тестами (МИС и ПТР)")


def charts_driver(df_all: pd.DataFrame):
    df = df_all[df_all["instrument_id"] == "driver"].copy()
    if df.empty:
        st.info("Нет данных по Ведущему драйверу")
        return

    DRIVER_ORDER = ["Будь совершенным", "Радуй других", "Спеши", "Будь сильным", "Старайся"]

    # ── Стековая гистограмма: распределение уровней по драйверам ─────────────
    st.subheader("Распределение уровней по каждому драйверу")
    level_order = ["Низкий", "Средний", "Ведущий"]
    stacked = df.groupby(["scale_name", "label"]).size().reset_index(name="n")
    stacked["label"] = pd.Categorical(stacked["label"], categories=level_order, ordered=True)
    stacked["scale_name"] = pd.Categorical(stacked["scale_name"], categories=DRIVER_ORDER, ordered=True)
    stacked = stacked.sort_values(["scale_name", "label"])
    total_per_scale = stacked.groupby("scale_name")["n"].transform("sum")
    stacked["pct"] = (stacked["n"] / total_per_scale * 100).round(1)

    fig = px.bar(
        stacked, x="pct", y="scale_name", color="label",
        orientation="h", barmode="stack",
        color_discrete_map=LEVEL_COLORS,
        labels={"pct": "% участников", "scale_name": "Драйвер", "label": "Уровень"},
        text=stacked["pct"].apply(lambda x: f"{x}%" if x >= 8 else ""),
        category_orders={"label": level_order},
    )
    fig.update_layout(xaxis_range=[0, 100], legend_title="Уровень")
    st.plotly_chart(fig, use_container_width=True)

    # ── Радарная диаграмма: средние баллы по группам ──────────────────────────
    st.subheader("Профиль драйверов — средние баллы по группе")

    # Попробуем разбить на группы по ПТР, если данные есть
    df_ptr = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
        ["respondent_id", "label"]
    ].rename(columns={"label": "ptr_level"})

    df_radar = df.merge(df_ptr, on="respondent_id", how="left")
    df_radar["ptr_level"] = df_radar["ptr_level"].fillna("Все участники")

    groups = df_radar["ptr_level"].unique().tolist()
    fig2 = go.Figure()

    for group in groups:
        subset = df_radar[df_radar["ptr_level"] == group]
        means = (
            subset.groupby("scale_name")["raw_score"].mean().reindex(DRIVER_ORDER).round(2)
        )
        fig2.add_trace(go.Scatterpolar(
            r=means.tolist() + [means.iloc[0]],
            theta=DRIVER_ORDER + [DRIVER_ORDER[0]],
            fill="toself",
            name=group,
        ))

    fig2.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
        legend_title="Группа (уровень ПТР)",
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Групповой Box-plot: ведущий драйвер × ПТР ────────────────────────
    st.subheader("Уровень ПТР по типу ведущего драйвера")
    df_ptr_score = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
        ["respondent_id", "raw_score"]
    ].rename(columns={"raw_score": "ptr_total"})

    # Определяем ведущий драйвер для каждого участника (максимальный балл)
    driver_wide = df.pivot_table(
        index="respondent_id", columns="scale_name", values="raw_score", aggfunc="first",
    )
    if not driver_wide.empty:
        leading = driver_wide.idxmax(axis=1).reset_index()
        leading.columns = ["respondent_id", "Ведущий драйвер"]
        leading_with_ptr = leading.merge(df_ptr_score, on="respondent_id", how="inner")

        if len(leading_with_ptr) >= 2:
            fig_box = px.box(
                leading_with_ptr, x="Ведущий драйвер", y="ptr_total",
                points="all", color="Ведущий драйвер",
                labels={"ptr_total": "Балл ПТР", "Ведущий драйвер": "Ведущий драйвер"},
                category_orders={"Ведущий драйвер": DRIVER_ORDER},
            )
            fig_box.update_layout(showlegend=False)
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            st.info("Нужно минимум 2 участника с обоими тестами")

    # ── Pie: распространённость драйверов в группах ПТР ──────────────────
    st.subheader("Ведущий драйвер в группах по уровню ПТР")
    if not driver_wide.empty:
        df_ptr_level = df_all[(df_all["instrument_id"] == "ptr") & (df_all["scale_id"] == "total")][
            ["respondent_id", "label"]
        ].rename(columns={"label": "ptr_level"})
        leading_with_level = leading.merge(df_ptr_level, on="respondent_id", how="inner")

        ptr_groups = [g for g in ["Высокий", "Низкий"] if g in leading_with_level["ptr_level"].values]
        if ptr_groups:
            cols = st.columns(len(ptr_groups))
            for i, level in enumerate(ptr_groups):
                subset = leading_with_level[leading_with_level["ptr_level"] == level]
                with cols[i]:
                    st.write(f"**ПТР: {level}** ({len(subset)} чел.)")
                    fig_pie = px.pie(
                        subset, names="Ведущий драйвер",
                        category_orders={"Ведущий драйвер": DRIVER_ORDER},
                    )
                    fig_pie.update_traces(textinfo="percent+label")
                    st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Нужны участники с разными уровнями ПТР")


def charts_general(df_all: pd.DataFrame):
    """Общая матрица корреляций: ПТР, Ио, MSTAT, Самоценность, Саморуководство, Самообвинение."""
    key_scales = {
        "ПТР (общий)": ("ptr", "total"),
        "Ио (интернальность)": ("usk", "io"),
        "MSTAT-1 (толерантность)": ("mstat1", "T"),
        "Самоценность (МИС)": ("mis", "scen"),
        "Саморуководство (МИС)": ("mis", "sruk"),
        "Самообвинение (МИС)": ("mis", "sobv"),
    }

    frames = []
    for label, (instr_id, scale_id) in key_scales.items():
        sub = df_all[(df_all["instrument_id"] == instr_id) & (df_all["scale_id"] == scale_id)][
            ["respondent_id", "raw_score"]
        ].rename(columns={"raw_score": label})
        frames.append(sub)

    if not frames:
        st.info("Недостаточно данных")
        return

    merged = frames[0]
    for f in frames[1:]:
        merged = merged.merge(f, on="respondent_id", how="inner")

    if len(merged) < 3:
        st.info("Нужно минимум 3 участника, прошедших все 5 методик")
        return

    st.subheader("Матрица корреляций (ключевые шкалы)")
    st.caption(
        "Положительные корреляции (синие) подтверждают связь ПТР с интернальностью, "
        "толерантностью и самоценностью. Отрицательные (красные) — связь с самообвинением."
    )

    corr_cols = list(key_scales.keys())
    corr = merged[corr_cols].corr().round(2)
    fig = px.imshow(
        corr, text_auto=True, color_continuous_scale="RdBu_r",
        zmin=-1, zmax=1, aspect="auto",
    )
    fig.update_layout(xaxis_title="", yaxis_title="", height=500)
    st.plotly_chart(fig, use_container_width=True)


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

    # ── Excel export ─────────────────────────────────────────────────────
    def build_excel(df_all: pd.DataFrame) -> bytes:
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            # Лист 1 — Сводная
            df_all["column"] = df_all["instrument_id"] + "_" + df_all["scale_id"]
            pivot = df_all.pivot_table(
                index="respondent_id", columns="column", values="raw_score", aggfunc="first",
            ).reset_index()
            pivot.columns.name = None
            pivot.to_excel(writer, sheet_name="Сводная", index=False)

            # Лист 2 — Детали
            detail_cols = ["respondent_id", "instrument_id", "scale_name",
                           "raw_score", "label", "interpretation", "calculated_at"]
            df_det = df_all[detail_cols].copy()
            df_det.columns = ["Участник", "Методика", "Шкала", "Балл",
                              "Уровень", "Интерпретация", "Дата"]
            df_det.to_excel(writer, sheet_name="Детали", index=False)

            # Лист 3 — Средние
            group = (
                df_all.groupby(["instrument_id", "scale_id", "scale_name"])["raw_score"]
                .agg(n="count", mean="mean", min="min", max="max", std="std")
                .round(2).reset_index()
            )
            group.columns = ["Методика", "Шкала (id)", "Шкала", "N",
                             "Среднее", "Min", "Max", "Std"]
            group.to_excel(writer, sheet_name="Средние", index=False)

            # Лист 4 — Участники (демография)
            with init_db(DB_PATH) as conn:
                resp_rows = query_respondents(conn)
            if resp_rows:
                df_resp = pd.DataFrame(resp_rows)
                df_resp.columns = ["Участник", "Возраст", "Возраст ребёнка", "Пол"]
                df_resp.to_excel(writer, sheet_name="Участники", index=False)

        return buf.getvalue()

    if st.button("📥 Экспорт в Excel", use_container_width=True):
        all_rows = load_data()
        if all_rows:
            xlsx = build_excel(pd.DataFrame(all_rows))
            st.session_state["excel_data"] = xlsx
        else:
            st.warning("Нет данных для экспорта")

    if "excel_data" in st.session_state:
        st.download_button(
            "⬇ Скачать .xlsx",
            data=st.session_state["excel_data"],
            file_name="results_all.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # ── Удаление участника ──────────────────────────────────────────────
    st.divider()
    st.subheader("Удалить участника")
    all_respondents = sorted(df_all["respondent_id"].unique().tolist())
    del_respondent = st.selectbox("Выберите участника", all_respondents, key="del_resp")
    if st.button("🗑 Удалить", use_container_width=True):
        st.session_state["confirm_delete"] = del_respondent

    if "confirm_delete" in st.session_state:
        name = st.session_state["confirm_delete"]
        st.warning(f"Удалить **{name}** и все результаты?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Да, удалить", type="primary", use_container_width=True):
                with init_db(DB_PATH) as conn:
                    delete_respondent(conn, name)
                del st.session_state["confirm_delete"]
                st.rerun()
        with c2:
            if st.button("Отмена", use_container_width=True):
                del st.session_state["confirm_delete"]
                st.rerun()

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
tab1, tab2, tab3, tab4 = st.tabs([
    "Сводная таблица", "Детальные результаты", "Средние по группе", "📈 Диаграммы"
])

with tab1:
    st.subheader("Один ряд на участника — баллы по всем шкалам")
    df["column"] = df["instrument_id"] + "_" + df["scale_id"]
    pivot = df.pivot_table(
        index="respondent_id", columns="column", values="raw_score", aggfunc="first",
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

    def highlight_level(row):
        colors = {
            "Высокий": "#d4edda", "Средний": "#fff3cd", "Низкий": "#f8d7da",
            "Ведущий": "#d4edda",
            "Толерантность": "#d4edda", "Нейтральный": "#fff3cd", "Интолерантность": "#f8d7da",
        }
        color = colors.get(row["Уровень"], "")
        return [f"background-color: {color}" if color else ""] * len(row)

    st.dataframe(df_detail.style.apply(highlight_level, axis=1), use_container_width=True, hide_index=True)
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

with tab4:
    # Диаграммы всегда строятся по ВСЕМ данным (фильтры не применяются)
    st.caption("Диаграммы строятся по всем собранным данным, независимо от фильтров.")

    sec1, sec2, sec3, sec4, sec5, sec6 = st.tabs([
        "ПТР", "MSTAT-1", "Ведущий драйвер", "УСК", "МИС", "🔗 Общая"
    ])

    with sec1:
        charts_ptr(df_all)
    with sec2:
        charts_mstat(df_all)
    with sec3:
        charts_driver(df_all)
    with sec4:
        charts_usk(df_all)
    with sec5:
        charts_mis(df_all)
    with sec6:
        charts_general(df_all)
