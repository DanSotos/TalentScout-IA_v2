"""
decision_maker.py - Módulo 4: Toma de decisiones + XAI
Clasifica vacantes en Alta / Media / Baja compatibilidad y genera explicaciones.
"""
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from config import (
    COSINE_SIMILARITY_THRESHOLD_HIGH,
    COSINE_SIMILARITY_THRESHOLD_MEDIUM,
    ENABLE_XAI,
    MAX_KEYWORDS_FOR_EXPLANATION,
)
from models.sentence_bert import SentenceBERTProcessor
from scrapers.computrabajo import Vacancy
from semantic_filter import compute_weighted_similarity


@dataclass
class Decision:
    compatibility_level: str   # "ALTA" | "MEDIA" | "BAJA"
    similarity_score: float
    explanation: str
    recommended_action: str


class DecisionMaker:
    """Toma decisiones sobre cada vacante y genera explicaciones XAI."""

    def __init__(self, processor: SentenceBERTProcessor):
        self.processor = processor

    def make_decision(self, cv_text: str, vacancy: Vacancy, score: float = None) -> Decision:
        if score is None:
            cv_emb = self.processor.generate_cv_embedding(cv_text)
            score = compute_weighted_similarity(self.processor, cv_emb, vacancy)

        if score >= COSINE_SIMILARITY_THRESHOLD_HIGH:
            level = "ALTA"
            action = "Postular automáticamente"
        elif score >= COSINE_SIMILARITY_THRESHOLD_MEDIUM:
            level = "MEDIA"
            action = "Revisión manual recomendada"
        else:
            level = "BAJA"
            action = "Descartar"

        explanation = ""
        if ENABLE_XAI:
            explanation = self._generate_explanation(cv_text, vacancy, score)

        return Decision(
            compatibility_level=level,
            similarity_score=round(score, 4),
            explanation=explanation,
            recommended_action=action,
        )

    def _generate_explanation(
        self, cv_text: str, vacancy: Vacancy, score: float
    ) -> str:
        cv_lower = cv_text.lower()
        matched = [r for r in vacancy.requirements if r.lower() in cv_lower]
        missing = [r for r in vacancy.requirements if r.lower() not in cv_lower]

        parts = [f"Similitud semántica: {score:.0%}."]
        if matched:
            parts.append(f"Skills coincidentes: {', '.join(matched[:MAX_KEYWORDS_FOR_EXPLANATION])}.")
        if missing:
            parts.append(f"Skills faltantes: {', '.join(missing[:MAX_KEYWORDS_FOR_EXPLANATION])}.")
        return " ".join(parts)