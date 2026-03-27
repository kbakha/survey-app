from pathlib import Path

import streamlit as st

from db import init_db, query_results, save_results
from loader import load_instruments
from scorer import calculate, validate

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "survey.db"

st.set_page_config(
    page_title="Психологическое исследование",
    page_icon="📋",
    layout="centered",
)

# ── Load instruments once ─────────────────────────────────────────────────────
@st.cache_resource
def get_instruments():
    return load_instruments(BASE_DIR / "config")


INSTRUMENTS = get_instruments()

def get_conn():
    return init_db(DB_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────
def already_submitted(respondent_id: str, instrument_id: str) -> bool:
    with get_conn() as conn:
        rows = query_results(conn, instrument_id=instrument_id, respondent_id=respondent_id)
    return len(rows) > 0


def init_state():
    defaults = {
        "page": "welcome",
        "respondent_id": "",
        "instrument_id": None,
        "answers": {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Pages ─────────────────────────────────────────────────────────────────────
def page_welcome():
    st.title("📋 Психологическое исследование")
    st.write("Введите ваше имя и выберите методику для прохождения.")
    st.divider()

    name = st.text_input("Ваше имя", placeholder="Имя Фамилия")

    instrument_id = st.selectbox(
        "Методика",
        options=sorted(INSTRUMENTS.keys(), key=lambda x: INSTRUMENTS[x].name),
        format_func=lambda x: INSTRUMENTS[x].name,
    )

    st.divider()

    if st.button("Начать тест →", type="primary", use_container_width=True):
        if not name.strip():
            st.error("Пожалуйста, введите ваше имя.")
            return
        if already_submitted(name.strip(), instrument_id):
            st.warning(
                f"Вы уже проходили этот тест. "
                f"Обратитесь к исследователю, если нужно пройти повторно."
            )
            return
        st.session_state.respondent_id = name.strip()
        st.session_state.instrument_id = instrument_id
        st.session_state.answers = {}
        st.session_state.page = "survey"
        st.rerun()


def page_survey():
    cfg = INSTRUMENTS[st.session_state.instrument_id]
    respondent = st.session_state.respondent_id

    st.title(cfg.name)
    st.caption(f"Участник: **{respondent}**")

    if cfg.instruction:
        st.info(cfg.instruction.strip())

    st.divider()

    # Build label list: "1 — Совершенно не согласен", etc.
    scores = cfg.scale_values if cfg.scale_values else list(range(cfg.min_score, cfg.max_score + 1))
    if cfg.scale_labels:
        radio_labels = [f"{v} — {l}" for v, l in zip(scores, cfg.scale_labels)]
    else:
        radio_labels = [str(v) for v in scores]

    answers = {}

    for item in cfg.items:
        q_num = item["n"]
        q_text = item["text"]

        selected = st.radio(
            label=f"**{q_num}.** {q_text}",
            options=scores,
            format_func=lambda v, rl=radio_labels, sv=scores: rl[sv.index(v)],
            index=None,
            key=f"q_{q_num}",
            horizontal=True,
        )

        if selected is not None:
            answers[q_num] = selected

        st.divider()

    # Progress
    answered = len(answers)
    remaining = cfg.n_items - answered
    progress = answered / cfg.n_items

    col1, col2 = st.columns([3, 1])
    with col1:
        st.progress(progress)
    with col2:
        st.caption(f"{answered} / {cfg.n_items}")

    if remaining > 0:
        st.warning(f"Осталось ответить: **{remaining}**")

    if st.button(
        "Отправить ответы ✓",
        type="primary",
        use_container_width=True,
        disabled=(remaining > 0),
    ):
        errors = validate(cfg, answers)
        if errors:
            for e in errors:
                st.error(e)
            return

        result = calculate(cfg, respondent, answers)
        with get_conn() as conn:
            save_results(conn, [result])

        st.session_state.page = "done"
        st.rerun()


def page_done():
    st.success("## Готово!")
    st.write(
        f"Спасибо, **{st.session_state.respondent_id}**! "
        f"Ваши ответы сохранены."
    )
    st.balloons()
    st.divider()

    if st.button("Пройти другой тест", use_container_width=True):
        st.session_state.page = "welcome"
        st.session_state.respondent_id = ""
        st.session_state.instrument_id = None
        st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────
init_state()

match st.session_state.page:
    case "welcome":
        page_welcome()
    case "survey":
        page_survey()
    case "done":
        page_done()
