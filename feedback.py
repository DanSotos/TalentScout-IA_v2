"""
feedback.py - Módulo 6: Retroalimentación adaptativa y brechas de habilidades
Registra resultados (incluyendo resultados de postulación) y detecta skills faltantes.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from config import LOGS_DIR


class FeedbackManager:
    """Registra feedback del usuario y detecta brechas de skills."""

    def __init__(self):
        self.feedback_file = LOGS_DIR / "feedback_history.json"
        self.history = self._load_history()

    def _load_history(self) -> List[dict]:
        if self.feedback_file.exists():
            try:
                return json.loads(self.feedback_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def save_run_summary(
        self,
        total_found: int,
        total_filtered: int,
        alta: int,
        media: int,
        baja: int,
        decisions: list = None,
        application_results: Optional[List[dict]] = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "total_found": total_found,
            "total_filtered": total_filtered,
            "alta": alta,
            "media": media,
            "baja": baja,
            "vacantes": [],
            "postulaciones": application_results or [],
        }

        if decisions:
            missing_skills_this_run = []
            for vacancy, decision in decisions:
                vac_entry = {
                    "titulo": vacancy.title,
                    "empresa": vacancy.company,
                    "ubicacion": vacancy.location,
                    "url": vacancy.url,
                    "fuente": vacancy.source,
                    "salario": vacancy.salary,
                    "compatibilidad": decision.compatibility_level,
                    "similitud": round(decision.similarity_score, 3),
                    "explicacion": decision.explanation,
                }
                entry["vacantes"].append(vac_entry)

                # Acumular skill gaps de vacantes ALTA/MEDIA no completamente cubiertas
                if decision.compatibility_level in ("ALTA", "MEDIA"):
                    gaps = self._extract_missing_skills(decision.explanation)
                    missing_skills_this_run.extend(gaps)

            if missing_skills_this_run:
                self.record_skill_gap(missing_skills_this_run)

        self.history.append(entry)
        self._save_history()
        print(f"   → Historial guardado en {self.feedback_file}")

    def record_skill_gap(self, missing_skills: List[str]) -> None:
        gap_file = LOGS_DIR / "skill_gaps.json"
        gaps: Dict[str, int] = {}
        if gap_file.exists():
            try:
                gaps = json.loads(gap_file.read_text(encoding="utf-8"))
            except Exception:
                gaps = {}
        for skill in missing_skills:
            skill = skill.strip().lower()
            if skill:
                gaps[skill] = gaps.get(skill, 0) + 1
        gap_file.write_text(json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_top_skill_gaps(self, top_n: int = 5) -> List[str]:
        gap_file = LOGS_DIR / "skill_gaps.json"
        if not gap_file.exists():
            return []
        gaps = json.loads(gap_file.read_text(encoding="utf-8"))
        sorted_gaps = sorted(gaps.items(), key=lambda x: x[1], reverse=True)
        return [s for s, _ in sorted_gaps[:top_n]]

    def _extract_missing_skills(self, explanation: str) -> List[str]:
        """Extrae skills faltantes del texto de explicación XAI."""
        marker = "Skills faltantes:"
        if marker not in explanation:
            return []
        part = explanation.split(marker)[-1]
        part = part.split(".")[0]  # hasta el primer punto
        return [s.strip() for s in part.split(",") if s.strip()]

    def _save_history(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.feedback_file.write_text(
            json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
