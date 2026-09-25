
import re
from typing import Dict, List, Optional

AREA_KEYWORDS: Dict[str, List[str]] = {
    "salud_biologia": [
        "biología", "biólogo", "bióloga", "laboratorio clínico", "microbiología",
        "bioquímica", "enfermería", "enfermero", "enfermera", "medicina", "médico",
        "tecnólogo médico", "tecnóloga médica", "hematología", "inmunología",
        "farmacia", "farmacéutico", "banco de sangre", "nutrición", "odontología",
        "salud", "clínico", "clínica",
    ],
    "ingenieria_mecanica_electronica": [
        "mecatrónica", "mecánica", "electrónica", "automatización", "plc",
        "autocad", "electricidad", "electricista", "industrial", "manufactura",
        "producción", "mantenimiento industrial", "planos", "instrumentación",
    ],
    "ingenieria_civil_arquitectura": [
        "ingeniería civil", "arquitectura", "arquitecto", "arquitecta",
        "construcción", "obra civil", "estructuras", "topografía",
    ],
    "tecnologia_datos": [
        "desarrollador", "desarrolladora", "programador", "programadora",
        "software", "ingeniería de sistemas", "data", "base de datos",
        "backend", "frontend", "fullstack", "machine learning", "devops",
        "ciencia de datos", "analista de datos", "python", "javascript", "sql",
    ],
    "administracion_negocios": [
        "administración de empresas", "negocios internacionales", "comercial",
        "ventas", "preventa", "postventa", "vendedor", "vendedora",
        "asesor comercial", "asesora comercial", "ejecutivo comercial",
        "ejecutiva comercial", "trade marketing", "marketing",
        "recursos humanos", "rrhh", "finanzas",
        "contabilidad", "contador", "contadora", "cumplimiento", "compliance",
        "kyc", "auditoría", "economía",
    ],
    "legal": [
        "derecho", "abogado", "abogada", "legal", "jurídico", "jurídica",
    ],
    "educacion": [
        "docente", "profesor", "profesora", "educación", "pedagogía",
    ],
}


def infer_area(text: str) -> Optional[str]:
    """
    Devuelve el rubro con más coincidencias de palabras clave en `text`,
    o None si no matchea ninguna (caso en que no se descarta nada).
    """
    if not text:
        return None

    text_low = text.lower()
    best_area, best_hits = None, 0

    for area, keywords in AREA_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text_low)
        if hits > best_hits:
            best_area, best_hits = area, hits

    return best_area


def career_matches(declared_career: str, vacancy_title: str, vacancy_requirements: Optional[List[str]] = None) -> bool:

    area_persona = infer_area(declared_career)

    texto_vacante = vacancy_title
    if vacancy_requirements:
        texto_vacante += " " + " ".join(vacancy_requirements)
    area_vacante = infer_area(texto_vacante)

    if area_persona is None or area_vacante is None:
        return True  # taxonomía no cubre uno de los dos lados: no descartar

    return area_persona == area_vacante