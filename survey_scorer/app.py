from pathlib import Path

import streamlit as st

from db import init_db, is_db_empty, seed_from_xlsx, query_respondents, query_results, save_respondent, save_results
from loader import load_instruments
from scorer import calculate, validate

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "survey.db"
SEED_PATH = BASE_DIR / "data" / "seed.xlsx"
SURVEY_CLOSED = st.secrets.get("SURVEY_CLOSED", True)  # управляется через secrets

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


# ── Seed DB on first run ─────────────────────────────────────────────────────
if SEED_PATH.exists():
    with get_conn() as conn:
        if is_db_empty(conn):
            seed_from_xlsx(conn, SEED_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────
def already_submitted(respondent_id: str, instrument_id: str) -> bool:
    with get_conn() as conn:
        rows = query_results(conn, instrument_id=instrument_id, respondent_id=respondent_id)
    return len(rows) > 0


def get_respondent_info(respondent_id: str) -> dict | None:
    with get_conn() as conn:
        rows = query_respondents(conn)
    for r in rows:
        if r["respondent_id"] == respondent_id:
            return r
    return None


def get_submitted_instruments(respondent_id: str) -> set:
    with get_conn() as conn:
        rows = query_results(conn, respondent_id=respondent_id)
    return {r["instrument_id"] for r in rows}


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

    st.markdown(
        "**Уважаемые родители!**\n\n"
        "Приглашаем вас принять участие в исследовании, посвящённом изучению пути, "
        "который проходит каждая семья, воспитывающая ребёнка с особыми потребностями. "
        "Ваш путь уникален, и ваш опыт может помочь многим другим."
    )

    st.write("Введите ваше имя и пройдите все 5 методик.")
    st.divider()

    # ── Имя (всегда видно) ───────────────────────────────────────────────
    name = st.text_input("Ваше имя", placeholder="Имя",
                         value=st.session_state.get("respondent_id", ""))

    # Проверяем, зарегистрирован ли уже этот респондент
    registered = False
    if name.strip():
        info = get_respondent_info(name.strip())
        if info and info.get("age") and info.get("gender"):
            registered = True

    if not registered:
        # ── Первый раз: заполни демографию ───────────────────────────────
        col1, col2 = st.columns(2)
        with col1:
            age = st.number_input(
                "Ваш возраст (полных лет)", min_value=18, max_value=100,
                value=25, step=1,
            )
        with col2:
            child_age = st.number_input(
                "Возраст Вашего ребенка с ООП (полных лет)", min_value=1, max_value=30,
                value=1, step=1,
            )

        gender = st.radio(
            "Укажите пол", options=["Мужской", "Женский"],
            horizontal=True, index=None,
        )
    else:
        st.info(
            f"С возвращением, **{name.strip()}**! "
            f"(возраст: {info['age']}, ребёнок: {info['child_age']}, пол: {info['gender']})"
        )

    # ── Методика ─────────────────────────────────────────────────────────
    sorted_ids = sorted(INSTRUMENTS.keys(), key=lambda x: INSTRUMENTS[x].name)
    submitted = get_submitted_instruments(name.strip()) if name.strip() else set()

    st.write("**Методика**")
    instrument_id = st.radio(
        "Методика",
        options=sorted_ids,
        format_func=lambda x: (
            INSTRUMENTS[x].name + (" ✅" if x in submitted else "")
        ),
        label_visibility="collapsed",
        index=None,
    )

    if submitted:
        remaining = len(INSTRUMENTS) - len(submitted)
        if remaining > 0:
            st.caption(f"Пройдено {len(submitted)} из {len(INSTRUMENTS)} методик")
        else:
            st.success("Все 5 методик пройдены!")

    st.divider()

    if st.button("Начать тест →", type="primary", use_container_width=True):
        if not name.strip():
            st.error("Пожалуйста, введите ваше имя.")
            return
        if not registered:
            if gender is None:
                st.error("Пожалуйста, укажите пол.")
                return
            with get_conn() as conn:
                save_respondent(conn, name.strip(), age, child_age, gender)
        if instrument_id is None:
            st.error("Пожалуйста, выберите методику.")
            return
        if instrument_id in submitted:
            st.warning(
                "Вы уже проходили этот тест. "
                "Обратитесь к исследователю, если нужно пройти повторно."
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
        # respondent_id сохраняем — чтобы не вводить данные повторно
        st.session_state.instrument_id = None
        st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────
def _unlock_survey():
    """Show admin login to unlock survey when SURVEY_CLOSED."""
    st.title("📋 Исследование завершено")
    st.info(
        "Сбор данных завершён. Спасибо всем участникам!\n\n"
        "Результаты доступны на странице **Результаты** (в боковом меню)."
    )
    st.divider()
    with st.expander("🔑 Вход для исследователя"):
        pwd = st.text_input("Пароль", type="password", key="survey_unlock_pwd")
        if st.button("Войти", key="survey_unlock_btn"):
            if pwd == st.secrets.get("ADMIN_PASSWORD", "admin123"):
                st.session_state.survey_unlocked = True
                st.rerun()
            else:
                st.error("Неверный пароль")


if SURVEY_CLOSED and not st.session_state.get("survey_unlocked", False):
    _unlock_survey()
else:
    init_state()

    match st.session_state.page:
        case "welcome":
            page_welcome()
        case "survey":
            page_survey()
        case "done":
            page_done()
