"""
utils/dedup.py - Deduplicación de vacantes

Evita que la misma vacante aparezca dos veces en una corrida (y con
distinto embedding/score) por scrapear el mismo aviso más de una vez,
o porque el portal lo devolvió repetido en dos páginas de resultados.
"""
from typing import List


def deduplicate_vacancies(vacancies: List) -> List:
    """
    Deduplica por (fuente, id) cuando existe, y si no, por URL.
    Conserva la primera aparición de cada vacante.
    """
    seen = set()
    result = []

    for v in vacancies:
        key = (v.source, v.id) if getattr(v, "id", None) else v.url
        if key in seen:
            continue
        seen.add(key)
        result.append(v)

    return result