
from config import CV_DIR, SIGNAL_TEXT_WEIGHT
from models.sentence_bert import SentenceBERTProcessor
from scrapers.computrabajo import Vacancy
from semantic_filter import compute_weighted_similarity
from utils.cv_parser import load_cv_from_directory


VACANTES_EJEMPLO = [
    # (título, requisitos_como_lista, "RELEVANTE" | "IRRELEVANTE", texto_descripcion)
    (
        "Analista de Laboratorio Clínico",
        ["Bioquímica", "Microbiología", "Control de calidad"],
        "RELEVANTE",
        "Buscamos bióloga/o para laboratorio clínico. Requisitos: colegiatura "
        "vigente, experiencia mínima de 2 años en análisis clínicos, "
        "disponibilidad inmediata. Beneficios: ingreso a planilla con todos "
        "los beneficios de ley, capacitaciones constantes.",
    ),
    (
        "Analista Preventa",
        [],
        "IRRELEVANTE",
        "Buscamos analista preventa para gestión comercial de clientes. "
        "Requisitos: experiencia mínima de 2 años en ventas, disponibilidad "
        "inmediata. Beneficios: ingreso a planilla con todos los beneficios "
        "de ley, capacitaciones constantes.",
    ),
    (
        "analista",
        [],
        "IRRELEVANTE",
        "Soluciones Empresariales y Consultoria SAC busca analista para "
        "unirse a su equipo. Requisitos: experiencia mínima de 2 años, "
        "disponibilidad inmediata. Beneficios: ingreso a planilla con todos "
        "los beneficios de ley, capacitaciones constantes.",
    ),
    (
        "Analista de Ingeniería Plano, Manufactura",
        ["AutoCAD", "Lectura de planos"],
        "IRRELEVANTE",
        "Buscamos analista de ingeniería para manejo de planos de "
        "manufactura. Requisitos: experiencia mínima de 3 años, "
        "disponibilidad inmediata. Beneficios: ingreso a planilla con todos "
        "los beneficios de ley, capacitaciones constantes.",
    ),
    (
        "Quality Control KYC Analyst - English Speaking",
        ["KYC", "AML", "Inglés avanzado"],
        "IRRELEVANTE",
        "Buscamos analista de control de calidad KYC con inglés avanzado. "
        "Requisitos: experiencia mínima de 2 años en cumplimiento, "
        "disponibilidad inmediata. Beneficios: ingreso a planilla con todos "
        "los beneficios de ley, capacitaciones constantes.",
    ),
]


def main():
    print("Cargando CV real...")
    cv_text = load_cv_from_directory(CV_DIR, "cv.pdf")

    processor = SentenceBERTProcessor()
    processor.load_model()
    cv_emb = processor.generate_cv_embedding(cv_text)


    max_len = getattr(processor.model, "max_seq_length", None)
    n_palabras = len(cv_text.split())
    tokenizer = getattr(processor.model, "tokenizer", None)
    n_tokens = len(tokenizer.tokenize(cv_text)) if tokenizer else None

    print(f"\n⚠ DIAGNÓSTICO DE TRUNCAMIENTO")
    print(f"   max_seq_length del modelo : {max_len} tokens")
    print(f"   Tu CV tiene               : {n_palabras} palabras"
          + (f" / {n_tokens} tokens" if n_tokens is not None else ""))
    if max_len and n_tokens and n_tokens > max_len:
        print(f"   🚨 TU CV SE ESTÁ CORTANDO: solo se están usando los "
              f"primeros {max_len} tokens de {n_tokens}. Todo lo que "
              f"venga después (probablemente tu Educación/Experiencia "
              f"real) NO está llegando al embedding.")
    print()

    print(f"\n{'Título':<45} {'Etiqueta':<12} {'signal':>7} {'full':>7} {'combinada':>10}")
    print("-" * 90)

    for titulo, reqs, etiqueta, descripcion in VACANTES_EJEMPLO:
        v = Vacancy(
            id="calib",
            title=titulo,
            company="",
            location="",
            description=descripcion,
            requirements=reqs,
        )
        signal_emb = processor.generate_vacancy_embedding(v.get_signal_text())
        full_emb = processor.generate_vacancy_embedding(v.get_full_text())
        sim_signal = processor.compute_cosine_similarity(cv_emb, signal_emb)
        sim_full = processor.compute_cosine_similarity(cv_emb, full_emb)
        combinada = SIGNAL_TEXT_WEIGHT * sim_signal + (1 - SIGNAL_TEXT_WEIGHT) * sim_full

        print(f"{titulo:<45} {etiqueta:<12} {sim_signal:>6.3f} {sim_full:>6.3f} {combinada:>9.3f}")

    print(
        "\nBusca el 'hueco' entre las combinadas de IRRELEVANTE y "
        "RELEVANTE. Pon COSINE_SIMILARITY_THRESHOLD_HIGH justo en ese "
        "hueco (o un poco por encima del techo de IRRELEVANTE)."
    )


if __name__ == "__main__":
    main()