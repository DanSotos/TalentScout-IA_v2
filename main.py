"""
main.py - Orquestador principal del job-agent
"""
import argparse
from pathlib import Path
from typing import List

from config import CV_DIR, AUTO_APPLY_HIGH_COMPATIBILITY
from models.sentence_bert import SentenceBERTProcessor
from scrapers import CompuTrabajoScraper, LinkedInScraper, IndeedScraper
from semantic_filter import SemanticFilter
from decision_maker import DecisionMaker
from applicator import SupervisedApplicator
from feedback import FeedbackManager
from utils.cv_parser import load_cv_from_directory


def parse_args():
    parser = argparse.ArgumentParser(description="Job Agent")
    parser.add_argument("--cv", type=str, default="cv.pdf")
    parser.add_argument("--keywords", type=str, default="desarrollador python javascript")
    parser.add_argument("--location", type=str, default="Lima")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument(
        "--mode",
        choices=["supervised", "auto", "review"],
        default="supervised",
        help=(
            "supervised: confirmación por vacante (recomendado) | "
            "auto: postula ALTA sin confirmar | "
            "review: solo muestra resultados, no postula"
        ),
    )
    return parser.parse_args()


def load_user_cv(cv_filename: str) -> str:
    print("[1] Cargando CV...")
    try:
        cv_text = load_cv_from_directory(CV_DIR, cv_filename)
        print(f"✓ CV cargado: {cv_filename}")
        return cv_text
    except FileNotFoundError as e:
        print(f"⚠ {e}")
        print("Usando CV mockeado para demostración...")
        return """
        Juan Pérez - Desarrollador Python
        Email: juan@example.com

        EXPERIENCIA:
        - Desarrollador Python Sr (2020-actual)
          FastAPI, Django, PostgreSQL, Docker, AWS

        HABILIDADES:
        Python, Django, FastAPI, PostgreSQL, MongoDB,
        Docker, AWS, Machine Learning, SQL, Git

        EDUCACIÓN:
        Ingeniería de Sistemas, Universidad de Lima (2018)
        """


def search_vacancies(keywords: str, location: str, limit: int) -> List:
    print("\n[2] Buscando vacantes...")
    scrapers = [
        ("Computrabajo", CompuTrabajoScraper()),
        ("LinkedIn",     LinkedInScraper()),
        ("Indeed",       IndeedScraper()),
    ]
    all_vacancies = []
    for name, scraper in scrapers:
        try:
            vacancies = scraper.search(keywords, location, limit // len(scrapers))
            all_vacancies.extend(vacancies)
            print(f"   → {name}: {len(vacancies)} vacantes encontradas")
        except Exception as e:
            print(f"   ⚠ Error en {name}: {e}")
    print(f"✓ Total: {len(all_vacancies)} vacantes")
    return all_vacancies


def main():
    args = parse_args()
    cv_text = load_user_cv(args.cv)

    print("\n" + "=" * 60)
    print("=== JOB-AGENT INICIANDO ===")
    print(f"=== MODO: {args.mode.upper()} ===")
    print("=" * 60)

    # ── 1. Embedding del CV ────────────────────────────────────────
    print("\n[3] Generando embedding del CV...")
    processor = SentenceBERTProcessor()
    processor.load_model()
    cv_embedding = processor.generate_cv_embedding(cv_text)
    print(f"✓ Embedding generado ({len(cv_embedding)} dimensiones)")

    # ── 2. Buscar vacantes ─────────────────────────────────────────
    all_vacancies = search_vacancies(args.keywords, args.location, args.limit)

    if not all_vacancies:
        print("⚠ No se encontraron vacantes")
        return

    # ── 3. Filtrado semántico ──────────────────────────────────────
    print("\n[4] Filtrado semántico...")
    semantic_filter = SemanticFilter(processor)
    filtered = semantic_filter.filter_vacancies(cv_embedding, all_vacancies)
    print(f"✓ {len(filtered)} vacantes pasaron el filtro")

    # ── 4. Decisiones ─────────────────────────────────────────────
    print("\n[5] Análisis de compatibilidad...")
    decision_maker = DecisionMaker(processor)
    decisions = []

    for vacancy, score in filtered:
        decision = decision_maker.make_decision(cv_text, vacancy, score)
        decisions.append((vacancy, decision))

        symbol = {"ALTA": "✅", "MEDIA": "📋", "BAJA": "❌"}.get(
            decision.compatibility_level, "?"
        )
        print(f"\n{symbol} {vacancy.title}")
        print(f"   Empresa   : {vacancy.company}")
        print(f"   Similitud : {decision.similarity_score:.2f}")
        print(f"   Nivel     : {decision.compatibility_level}")
        print(f"   {decision.explanation}")

    # ── 5. Resumen ─────────────────────────────────────────────────
    alta  = sum(1 for _, d in decisions if d.compatibility_level == "ALTA")
    media = sum(1 for _, d in decisions if d.compatibility_level == "MEDIA")
    baja  = sum(1 for _, d in decisions if d.compatibility_level == "BAJA")

    print("\n" + "=" * 60)
    print("[6] RESUMEN:")
    print(f"   ✅ Alta compatibilidad : {alta}")
    print(f"   📋 Revisión manual     : {media}")
    print(f"   ❌ Descartadas         : {baja}")
    print("=" * 60)

    # ── 6. Postulación según modo ──────────────────────────────────
    application_results = []

    if args.mode == "review":
        print("\n[7] Modo REVISIÓN: no se realizan postulaciones.")

    elif args.mode == "supervised":
        vacantes_a_procesar = [
            (v, d) for v, d in decisions
            if d.compatibility_level in ("ALTA", "MEDIA")
        ]
        if not vacantes_a_procesar:
            print("\n[7] No hay vacantes ALTA o MEDIA para procesar.")
        else:
            print(f"\n[7] POSTULACIÓN SUPERVISADA")
            print(f"    Se procesarán {len(vacantes_a_procesar)} vacantes "
                  f"(ALTA + MEDIA).")
            print("    Para cada una se pedirá tu confirmación.\n")

            applicator = SupervisedApplicator()
            for vacancy, decision in vacantes_a_procesar:
                result = applicator.process(vacancy, cv_text, decision)
                application_results.append({
                    "vacancy_id": vacancy.id,
                    "title": vacancy.title,
                    "company": vacancy.company,
                    **result,
                })

            sent      = sum(1 for r in application_results if r["status"] == "ENVIADA")
            fallback  = sum(1 for r in application_results if r["status"] == "FALLBACK_MANUAL")
            postponed = sum(1 for r in application_results if r["status"] == "POSPUESTA")
            skipped   = sum(1 for r in application_results if r["status"] == "DESCARTADA")

            print("\n" + "─" * 60)
            print("  RESULTADO DE POSTULACIONES:")
            print(f"  ✅ Enviadas           : {sent}")
            print(f"  📋 Fallback manual    : {fallback}")
            print(f"  📌 Pospuestas         : {postponed}")
            print(f"  ❌ Descartadas        : {skipped}")
            print("─" * 60)

    elif args.mode == "auto":
        if AUTO_APPLY_HIGH_COMPATIBILITY and alta > 0:
            print("\n[7] Modo AUTO: postulando vacantes de alta compatibilidad...")
            from applicator import Applicator
            applicator = Applicator()
            for vacancy, decision in decisions:
                if decision.compatibility_level == "ALTA":
                    applicator.prepare_application(vacancy, cv_text)
            print(f"✓ {alta} postulaciones preparadas")
        else:
            print("\n[7] Modo AUTO: sin vacantes de alta compatibilidad.")

    # ── 7. Feedback ────────────────────────────────────────────────
    print("\n[8] Guardando feedback...")
    feedback_manager = FeedbackManager()
    feedback_manager.save_run_summary(
        len(all_vacancies),
        len(filtered),
        alta, media, baja,
        decisions=decisions,
        application_results=application_results,
    )
    print("✓ Listo!")

    print("\n=== EJECUCIÓN COMPLETA ===")


if __name__ == "__main__":
    main()