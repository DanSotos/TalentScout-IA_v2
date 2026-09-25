
import sys
import io
import json


sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from scrapers.computrabajo import Vacancy
from applicator import SupervisedApplicator


class _Decision:
    """Reconstruye un objeto 'decision' mínimo a partir del JSON recibido."""
    def __init__(self, d: dict):
        self.compatibility_level = d["compatibility_level"]
        self.similarity_score = d["similarity_score"]
        self.explanation = d["explanation"]


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)

    vacancy = Vacancy(**payload["vacancy"])
    decision = _Decision(payload["decision"])
    cv_text = payload["cv_text"]

    applicator = SupervisedApplicator()
    result = applicator.process(vacancy, cv_text, decision)


    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()