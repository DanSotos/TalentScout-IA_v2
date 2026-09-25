from typing import List, Optional, Tuple
import numpy as np
from config import COSINE_SIMILARITY_THRESHOLD_MEDIUM, SIGNAL_TEXT_WEIGHT
from models.sentence_bert import SentenceBERTProcessor
from scrapers.computrabajo import Vacancy
from utils.career_filter import career_matches


def compute_weighted_similarity(
    processor: SentenceBERTProcessor,
    query_embedding: np.ndarray,
    vacancy: Vacancy,
    signal_weight: float = SIGNAL_TEXT_WEIGHT,
) -> float:
    """Similitud ponderada entre un embedding de consulta (puede ser el del
    CV o el de una preferencia de cargo escrita a mano) y una vacante."""

    signal_emb = processor.generate_vacancy_embedding(vacancy.get_signal_text())
    full_emb = processor.generate_vacancy_embedding(vacancy.get_full_text())

    sim_signal = processor.compute_cosine_similarity(query_embedding, signal_emb)
    sim_full = processor.compute_cosine_similarity(query_embedding, full_emb)

    return signal_weight * sim_signal + (1 - signal_weight) * sim_full


class SemanticFilter:
    """Filtra vacantes por similitud semántica con el CV, y opcionalmente
    con el cargo/preferencia laboral declarado por el usuario."""

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
        cargo_embedding: Optional[np.ndarray] = None,
        cargo_weight: float = 0.35,
    ) -> List[Tuple[Vacancy, float]]:
       
        results = []
        for v in vacancies:
            if declared_career and not career_matches(declared_career, v.title, v.requirements):
                continue

            score_area = self.compute_similarity(cv_embedding, v)

            if cargo_embedding is not None:
                score_cargo = compute_weighted_similarity(self.processor, cargo_embedding, v)
                score = (1 - cargo_weight) * score_area + cargo_weight * score_cargo
            else:
                score = score_area

            if score >= threshold:
                results.append((v, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results