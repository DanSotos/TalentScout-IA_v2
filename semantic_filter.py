
from typing import List, Tuple
import numpy as np
from config import COSINE_SIMILARITY_THRESHOLD_MEDIUM, SIGNAL_TEXT_WEIGHT
from models.sentence_bert import SentenceBERTProcessor
from scrapers.computrabajo import Vacancy
from utils.career_filter import career_matches


def compute_weighted_similarity(
    processor: SentenceBERTProcessor,
    cv_embedding: np.ndarray,
    vacancy: Vacancy,
    signal_weight: float = SIGNAL_TEXT_WEIGHT,
) -> float:

    signal_emb = processor.generate_vacancy_embedding(vacancy.get_signal_text())
    full_emb = processor.generate_vacancy_embedding(vacancy.get_full_text())

    sim_signal = processor.compute_cosine_similarity(cv_embedding, signal_emb)
    sim_full = processor.compute_cosine_similarity(cv_embedding, full_emb)

    return signal_weight * sim_signal + (1 - signal_weight) * sim_full


class SemanticFilter:
    """Filtra vacantes por similitud semántica con el CV."""

    def __init__(self, processor: SentenceBERTProcessor):
        self.processor = processor

    def compute_similarity(
        self, cv_embedding: np.ndarray, vacancy: Vacancy
    ) -> float:
        return compute_weighted_similarity(self.processor, cv_embedding, vacancy)

    def filter_vacancies(
        self,
        cv_embedding: np.ndarray,
        vacancies: List[Vacancy],
        threshold: float = COSINE_SIMILARITY_THRESHOLD_MEDIUM,
        declared_career: str = "",
    ) -> List[Tuple[Vacancy, float]]:
        """
        declared_career: carrera/área declarada por la persona (ej.
        "Ingeniería Mecatrónica", "Biología"). Si se pasa, se aplica un
        filtro DURO por rubro antes de calcular similitud (ver
        utils/career_filter.py): si el rubro del título de la vacante
        se detecta como distinto al de la carrera declarada, se
        descarta sin importar qué tan alto salga el coseno. Si se deja
        vacío, el comportamiento es igual que antes (solo similitud).
        """
        results = []
        for v in vacancies:
            if declared_career and not career_matches(declared_career, v.title, v.requirements):
                continue
            score = self.compute_similarity(cv_embedding, v)
            if score >= threshold:
                results.append((v, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results