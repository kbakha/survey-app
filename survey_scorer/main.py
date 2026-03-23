import argparse
import sys
from pathlib import Path

from db import init_db, query_results, save_results
from loader import load_instruments, load_responses
from reporter import export_all
from scorer import calculate, validate


def run_calculate(args):
    config_dir = Path(args.config)
    input_path = Path(args.input)
    output_dir = Path(args.output)
    db_path = Path(args.db)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    instruments = load_instruments(config_dir)
    responses = load_responses(input_path)
    conn = init_db(db_path)

    score_results = []
    skipped = 0

    for entry in responses:
        respondent_id = entry["respondent_id"]
        instrument_id = entry["instrument_id"]
        answers = entry["answers"]

        if instrument_id not in instruments:
            print(f"WARNING: Неизвестная методика '{instrument_id}' "
                  f"для '{respondent_id}' — пропускается.")
            skipped += 1
            continue

        cfg = instruments[instrument_id]
        errors = validate(cfg, answers)
        if errors:
            print(f"WARNING: Ошибки валидации для '{respondent_id}' / '{instrument_id}':")
            for e in errors:
                print(f"  - {e}")
            skipped += 1
            continue

        result = calculate(cfg, respondent_id, answers)
        score_results.append(result)

    if score_results:
        saved = save_results(conn, score_results)
        print(f"Сохранено {saved} записей в {db_path} "
              f"({len(score_results)} респондентов, {skipped} пропущено)")
    else:
        print(f"Нет результатов для сохранения ({skipped} пропущено).")
        conn.close()
        return

    rows = query_results(conn)
    p1, p2, p3 = export_all(rows, output_dir)
    print(f"Экспорт:\n  {p1}\n  {p2}\n  {p3}")
    conn.close()


def run_export(args):
    db_path = Path(args.db)
    output_dir = Path(args.output)

    if not db_path.exists():
        print(f"ERROR: База данных не найдена: {db_path}")
        sys.exit(1)

    conn = init_db(db_path)
    rows = query_results(
        conn,
        instrument_id=args.filter_instrument,
        respondent_id=args.filter_respondent,
    )

    if not rows:
        print("В базе данных нет результатов (или ни один не прошёл фильтр).")
        conn.close()
        return

    p1, p2, p3 = export_all(rows, output_dir)
    print(f"Экспортировано {len(rows)} записей:\n  {p1}\n  {p2}\n  {p3}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Survey Scorer — подсчёт результатов психологических тестов",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--input",             help="Путь к CSV с ответами")
    parser.add_argument("--output",            default="results",  help="Папка для результатов (по умолчанию: results/)")
    parser.add_argument("--config",            default="config",   help="Папка с YAML-конфигами (по умолчанию: config/)")
    parser.add_argument("--db",                default="survey.db", help="Путь к SQLite-базе (по умолчанию: survey.db)")
    parser.add_argument("--export",            action="store_true", help="Экспорт из БД без пересчёта")
    parser.add_argument("--filter-instrument", default=None,        help="Фильтр экспорта по методике (например: ptr)")
    parser.add_argument("--filter-respondent", default=None,        help="Фильтр экспорта по участнику")

    args = parser.parse_args()

    if args.export:
        run_export(args)
    elif args.input:
        run_calculate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
