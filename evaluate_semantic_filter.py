
import argparse
import json
from pathlib import Path

from config import CV_DIR, DATA_DIR, COSINE_SIMILARITY_THRESHOLD_HIGH, COSINE_SIMILARITY_THRESHOLD_MEDIUM
from models.sentence_bert import SentenceBERTProcessor
from utils.cv_parser import load_cv_from_directory


def parse_args():
    parser = argparse.ArgumentParser(description="Evalúa precisión/recall del filtro semántico")
    parser.add_argument("--cv", type=str, default="cv.pdf")
    parser.add_argument(
        "--gold", type=str, default=str(DATA_DIR / "gold_standard.json"),
        help="Ruta al JSON etiquetado a mano"
    )
    parser.add_argument(
        "--threshold", type=float, default=COSINE_SIMILARITY_THRESHOLD_MEDIUM,
        help="Umbral de similitud a evaluar (por defecto: el umbral MEDIA actual)"
    )
    return parser.parse_args()


def compute_metrics(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
    }


def main():
    args = parse_args()

    gold_path = Path(args.gold)
    if not gold_path.exists():
        print(f"⚠ No existe {gold_path}.")
        print("  Copia data/gold_standard_ejemplo.json a data/gold_standard.json")
        print("  y complétalo con vacantes reales etiquetadas a mano.")
        return

    gold_set = json.loads(gold_path.read_text(encoding="utf-8"))
    if len(gold_set) < 10:
        print(f"⚠ Solo tienes {len(gold_set)} ejemplos etiquetados. "
              f"Se recomienda un mínimo de ~20-30 para que el resultado sea citable.")

    print("Cargando CV...")
    cv_text = load_cv_from_directory(CV_DIR, args.cv)

    print("Cargando modelo Sentence-BERT...")
    processor = SentenceBERTProcessor()
    processor.load_model()
    cv_embedding = processor.generate_cv_embedding(cv_text)

    y_true, y_pred, detalle = [], [], []

    for item in gold_set:
        vacancy_text = item["vacante_texto"]
        relevante_real = bool(item["relevante"])

        vac_embedding = processor.generate_vacancy_embedding(vacancy_text)
        score = processor.compute_cosine_similarity(cv_embedding, vac_embedding)
        relevante_predicho = score >= args.threshold

        y_true.append(relevante_real)
        y_pred.append(relevante_predicho)
        detalle.append({
            "titulo": item.get("vacante_titulo", "(sin título)"),
            "score": round(score, 3),
            "real": relevante_real,
            "predicho": relevante_predicho,
            "acierto": relevante_real == relevante_predicho,
        })

    metrics = compute_metrics(y_true, y_pred)

    print(f"\n=== Resultado con umbral = {args.threshold} ===")
    print(f"Precisión : {metrics['precision']:.2%}")
    print(f"Recall    : {metrics['recall']:.2%}")
    print(f"F1        : {metrics['f1']:.2%}")
    print(f"TP={metrics['tp']}  FP={metrics['fp']}  FN={metrics['fn']}  TN={metrics['tn']}")

    print("\n--- Detalle por vacante ---")
    for d in detalle:
        marca = "✓" if d["acierto"] else "✗"
        print(f"{marca} [{d['score']:.2f}] real={d['real']!s:5} predicho={d['predicho']!s:5}  {d['titulo']}")


if __name__ == "__main__":
    main()