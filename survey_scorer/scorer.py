from dataclasses import dataclass, field


@dataclass
class ScaleResult:
    scale_id: str
    scale_name: str
    raw_score: float
    level: str
    label: str
    interpretation: str


@dataclass
class ScoreResult:
    respondent_id: str
    instrument_id: str
    scales: list = field(default_factory=list)


def _find_level(norms, scale_id: str, score: float):
    for norm in norms:
        if norm.scale_id == scale_id and norm.min_val <= score <= norm.max_val:
            return norm.level, norm.label, norm.interpretation
    return "unknown", "Неизвестно", f"Балл {score} не входит ни в один диапазон норм"


def validate(instrument_cfg, answers: dict) -> list:
    valid_values = (
        set(instrument_cfg.scale_values)
        if instrument_cfg.scale_values
        else set(range(instrument_cfg.min_score, instrument_cfg.max_score + 1))
    )
    errors = []
    for i in range(1, instrument_cfg.n_items + 1):
        if i not in answers:
            errors.append(f"отсутствует ответ на вопрос {i}")
        elif answers[i] not in valid_values:
            errors.append(
                f"Q{i}={answers[i]} вне допустимого диапазона {sorted(valid_values)}"
            )
    return errors


def calculate(instrument_cfg, respondent_id: str, answers: dict) -> ScoreResult:
    result = ScoreResult(respondent_id=respondent_id, instrument_id=instrument_cfg.id)

    for scale in instrument_cfg.scales:
        if instrument_cfg.aggregation == "sum_subscales":
            score = sum(answers[i] for i in scale.direct_items)
            score += sum(instrument_cfg.max_score - answers[i] for i in scale.reverse_items)

        elif instrument_cfg.aggregation == "direct_minus_reverse":
            score = sum(answers[i] for i in scale.direct_items)
            score -= sum(answers[i] for i in scale.reverse_items)

        else:
            raise ValueError(f"Неизвестный тип агрегации: '{instrument_cfg.aggregation}'")

        level, label, interpretation = _find_level(instrument_cfg.norms, scale.id, score)
        result.scales.append(ScaleResult(
            scale_id=scale.id,
            scale_name=scale.name,
            raw_score=score,
            level=level,
            label=label,
            interpretation=interpretation,
        ))

    return result
