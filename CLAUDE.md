# Survey App — Project Knowledge Base

## What this project is

Academic research tool for collecting and scoring psychological survey data.
**Study:** Post-traumatic growth in parents of children with disabilities (n=35).
**Institution:** KazNPU named after Abai, Kazakhstan.
**Stack:** Python 3.10+, Streamlit, SQLite, YAML configs, Plotly.

---

## Directory structure

```
survery-app/
├── CLAUDE.md                      ← this file
├── .gitignore                     ← excludes опросники/, survey.db, secrets
├── опросники/                     ← source Word documents (gitignored)
│   ├── ПТР/
│   ├── MSTAT 1/
│   └── Ведущий драйвер/
└── survey_scorer/                 ← the application
    ├── app.py                     ← Streamlit entry point (survey form)
    ├── scorer.py                  ← scoring logic
    ├── loader.py                  ← YAML + CSV loading
    ├── db.py                      ← SQLite (init, save, query)
    ├── reporter.py                ← CSV export
    ├── main.py                    ← CLI entry point
    ├── requirements.txt
    ├── survey.db                  ← SQLite database (gitignored)
    ├── .gitignore
    ├── .streamlit/
    │   └── secrets.toml           ← ADMIN_PASSWORD (gitignored)
    ├── config/                    ← one YAML per instrument
    │   ├── ptr.yaml
    │   ├── mstat1.yaml
    │   └── driver.yaml
    ├── data/
    │   └── responses.csv          ← bulk import format (gitignored)
    ├── pages/
    │   └── admin.py               ← Streamlit admin page (password-protected)
    └── results/                   ← exported CSVs (gitignored)
```

---

## How to add a new instrument

1. **Create `config/<id>.yaml`** — follow the schema below
2. **Restart Streamlit** — it auto-discovers all YAMLs in `config/`
3. **No code changes needed** — unless the instrument requires a new `aggregation` type

That's it. The instrument appears in the survey dropdown and admin charts automatically.

---

## YAML config schema

```yaml
instrument:
  id: str                  # unique key used everywhere (e.g. "ptr")
  name: str                # full display name
  n_items: int             # total number of questions
  min_score: int           # minimum score per question
  max_score: int           # maximum score per question
  aggregation: str         # "sum_subscales" | "direct_minus_reverse"
  instruction: str         # shown to user before questions (optional)

scale_labels:              # list of strings, length = max_score - min_score + 1
  - "Label for min_score"
  - ...
  - "Label for max_score"

items:                     # list of all questions
  - {n: 1, text: "Question text"}
  - ...

scales:                    # scoring key
  - id: str
    name: str
    direct_items: [int, ...]   # question numbers summed directly
    reverse_items: [int, ...]  # inverted (sum_subscales) or subtracted (direct_minus_reverse)
    is_total: bool

norms:                     # interpretation ranges
  - scale_id: str
    level: str             # "low" | "medium" | "high" | "negative" | "neutral" | "positive" | "Ведущий"
    label: str             # display label
    min_val: float         # inclusive, can be negative
    max_val: float         # inclusive
    interpretation: str
```

### Aggregation types

| Type | Formula | Use case |
|---|---|---|
| `sum_subscales` | `Σ(direct_items) + Σ(max_score − reverse_items)` | PTR, Driver |
| `direct_minus_reverse` | `Σ(direct_items) − Σ(reverse_items)` | MSTAT-1 |

---

## Instruments currently configured

### 1. ПТР — Посттравматический рост (`ptr`)
- **Source:** Tedeschi & Calhoun (1996), adapted by Magomedeminov (2004)
- **Items:** 21, scale 0–5
- **Aggregation:** `sum_subscales`
- **Subscales (5) + total:**

| ID | Name | Items | Max |
|---|---|---|---|
| od | Отношение к другим | 6,8,9,15,16,20,21 | 35 |
| nv | Новые возможности | 3,7,11,14,17 | 25 |
| sl | Сила личности | 4,10,12,19 | 20 |
| di | Духовные изменения | 5,18 | 10 |
| pc | Повышение ценности жизни | 1,2,13 | 15 |
| total | Индекс ПТР | 1–21 | 105 |

- **Norms (total):** Low 0–32 / Medium 33–63 / High 64–105
- **Traumatic event context:** child's diagnosis / personal crisis
- **Sample results:** Гульбаршин=82 (High), Дильмурат=51 (Medium)

---

### 2. MSTAT-1 — Толерантность к неопределённости (`mstat1`)
- **Source:** D. McLain (1993), adapted by Lukovitskaya (1998) / Osin (2010)
- **Items:** 22, scale 1–7 (Likert)
- **Aggregation:** `direct_minus_reverse`
- **Formula:** T = Σ(direct) − Σ(reverse), range −66 to +66
- **Single scale:**

| Items type | Question numbers |
|---|---|
| Direct (tolerance → high score) | 4,7,11,12,14,15,17,18,19,21,22 |
| Reverse (intolerance → high score) | 1,2,3,5,6,8,9,10,13,16,20 |

- **Norms:** Negative (−66 to −1) / Neutral (0) / Positive (+1 to +66)
- **Sample results:** Гульбаршин=+14, Дильмурат=−12

---

### 3. Ведущий драйвер — Driver Questionnaire (`driver`)
- **Source:** Taibi Kahler (1974), transactional analysis
- **Items:** 25, scale 0–2 (Нет=0, В некоторой степени=1, Да=2)
- **Aggregation:** `sum_subscales`
- **5 drivers, 5 questions each:**

| ID | Driver | Items | Max |
|---|---|---|---|
| perfect | Будь совершенным | 1–5 | 10 |
| please | Радуй других | 6–10 | 10 |
| hurry | Спеши | 11–15 | 10 |
| strong | Будь сильным | 16–20 | 10 |
| try | Старайся | 21–25 | 10 |

- **Norms per scale:** Low 0–3 / Medium 4–6 / High (Ведущий) 7–10
- **A driver is "leading" at ≥7 points**
- **Sample results:** Гульбаршин → Спеши=7 (leading), Дильмурат → Будь совершенным=8 (leading)

---

## Database schema (SQLite)

```sql
CREATE TABLE respondents (
    respondent_id TEXT PRIMARY KEY
);

CREATE TABLE results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    respondent_id TEXT  NOT NULL,
    instrument_id TEXT  NOT NULL,
    scale_id      TEXT  NOT NULL,
    scale_name    TEXT  NOT NULL,
    raw_score     REAL  NOT NULL,
    level         TEXT  NOT NULL,
    label         TEXT  NOT NULL,
    interpretation TEXT NOT NULL,
    calculated_at TEXT  NOT NULL DEFAULT (datetime('now')),
    UNIQUE(respondent_id, instrument_id, scale_id)  -- INSERT OR REPLACE on rerun
);
```

---

## Application flow

### Survey (app.py)
1. `welcome` — user enters name, selects instrument
2. `survey` — all questions rendered with `st.radio(horizontal=True)`, submit locked until all answered
3. `done` — results saved to DB, balloons

### Admin (pages/admin.py)
- Password from `st.secrets["ADMIN_PASSWORD"]` (local: `.streamlit/secrets.toml`)
- 4 tabs: Сводная таблица / Детальные результаты / Средние по группе / 📈 Диаграммы
- Диаграммы tab has 3 sub-tabs (ПТР / MSTAT-1 / Ведущий драйвер):
  - **ПТР:** bar chart level distribution + pie chart + subscale averages bar
  - **MSTAT-1:** level distribution bar + scatter plot MSTAT-1 × PTR with trendline
  - **Driver:** stacked horizontal bar (level distribution per driver) + radar chart (group profile split by PTR level)

### CLI (main.py)
```bash
python main.py --input data/responses.csv   # calculate + save to DB + export CSV
python main.py --export                      # re-export from DB without recalculating
python main.py --export --filter-instrument ptr
python main.py --export --filter-respondent Гульбаршин
```

---

## Key implementation details

### Threading (Streamlit)
SQLite connections use `check_same_thread=False`. Connections are created per-call via `get_conn()` context manager — **never cached globally** (causes threading errors).

### Duplicate prevention
`already_submitted(respondent_id, instrument_id)` checks DB before allowing re-entry on welcome page.

### Scale labels
`scale_labels` list must have exactly `max_score - min_score + 1` entries. Radio options are rendered as `f"{value} — {label}"`.

### Norm lookup
First matching range wins. Ranges must be contiguous and cover the full possible score span to avoid `"unknown"` level.

### Charts (Plotly)
- Level colors: High/Ведущий/Толерантность → green `#4CAF50`, Medium/Нейтральный → amber `#FFC107`, Low/Интолерантность → red `#F44336`
- Radar chart for driver uses `DRIVER_ORDER = ["Будь совершенным", "Радуй других", "Спеши", "Будь сильным", "Старайся"]`
- Correlation scatter uses `plotly trendline="ols"` (requires statsmodels)

---

## Deployment

- **Platform:** Streamlit Community Cloud (free)
- **Secrets:** Set `ADMIN_PASSWORD` in Streamlit Cloud dashboard → Advanced settings → Secrets
- **DB persistence:** `survey.db` resets on redeploy → export CSV before pushing code updates
- **Run locally:** `.venv/bin/streamlit run app.py`

---

## How to process a new instrument document

When user provides a new methodology (Word .docx or description), extract:

1. **Instrument metadata:** name, author, year, n_items, min_score, max_score
2. **Scale labels:** the text descriptions for each score value
3. **All question texts** (in order, numbered)
4. **Scoring key:** which questions belong to which subscale
5. **Reverse items:** questions where higher score means opposite trait
6. **Aggregation type:** simple sum → `sum_subscales`; direct minus reverse → `direct_minus_reverse`
7. **Norm table:** ranges + labels + interpretation text for each scale
8. **Verify with sample respondent data** if available (cross-check computed vs documented scores)

Then create `config/<id>.yaml` following the schema above.

For admin charts, add a new `charts_<id>(df_all)` function in `pages/admin.py` and add a sub-tab in the Диаграммы section. Chart type should reflect the instrument structure:
- Single total score → distribution bar + pie
- Multiple subscales → subscale averages bar + optional radar
- If correlatable with PTR → add scatter plot
