"""
models/sentence_bert.py - Módulo 1: Procesamiento IA con Sentence-BERT
"""
import hashlib
import pickle
from typing import List, Optional, Dict
import numpy as np
from sentence_transformers import SentenceTransformer

from config import SENTENCE_BERT_MODEL, CACHE_DIR


class SentenceBERTProcessor:

    def __init__(self, model_name: str = SENTENCE_BERT_MODEL):
        self.model_name = model_name
        self.model: Optional[SentenceTransformer] = None
        self._cache_path = CACHE_DIR / f"embeddings_{model_name.replace('/', '_')}.pkl"
        self._cache: Dict[str, np.ndarray] = self._load_cache()

    def _load_cache(self) -> Dict[str, np.ndarray]:
        if self._cache_path.exists():
            try:
                with open(self._cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        try:
            with open(self._cache_path, "wb") as f:
                pickle.dump(self._cache, f)
        except Exception as e:
            print(f"⚠ No se pudo guardar el cache de embeddings: {e}")

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def load_model(self) -> None:
        if self.model is None:
            print(f"Cargando modelo: {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            
            print(f"✓ Modelo cargado correctamente")

    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Genera el embedding de un texto, usando cache en disco por hash
        de (modelo + texto exacto). Así, el mismo texto SIEMPRE produce
        el mismo score de similitud entre corridas distintas, y las
        vacantes repetidas no se vuelven a calcular.
        """
        key = self._hash_text(text)
        if key in self._cache:
            return self._cache[key]

        if self.model is None:
            self.load_model()
        embedding = self.model.encode(text, convert_to_numpy=True)

        self._cache[key] = embedding
        self._save_cache()
        return embedding

    def generate_cv_embedding(self, cv_text: str) -> np.ndarray:
        return self.generate_embedding(cv_text)

    def generate_vacancy_embedding(self, vacancy_description: str) -> np.ndarray:
        return self.generate_embedding(vacancy_description)

    def batch_generate_embeddings(self, texts: List[str]) -> np.ndarray:
        if self.model is None:
            self.load_model()
        return self.model.encode(texts, convert_to_numpy=True)

    def compute_cosine_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))


def create_processor() -> SentenceBERTProcessor:
    return SentenceBERTProcessor()