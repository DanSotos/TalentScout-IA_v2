
import sys
import io
import json



sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from scrapers import CompuTrabajoScraper, LinkedInScraper, IndeedScraper


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)

    keywords = payload["keywords"]
    location = payload["location"]
    limit = payload["limit"]

    scrapers = [
        ("Computrabajo", CompuTrabajoScraper()),
        ("LinkedIn", LinkedInScraper()),
        ("Indeed", IndeedScraper()),
    ]

    all_vacancies = []
    errores = {}

    for name, scraper in scrapers:
        try:
            vacancies = scraper.search(keywords, location, limit // len(scrapers))
            all_vacancies.extend(vacancies)
            print(f"   → {name}: {len(vacancies)} vacantes encontradas", file=sys.stderr)
        except Exception as e:
            errores[name] = f"{type(e).__name__}: {e}"
            print(f"   ⚠ Error en {name}: {e}", file=sys.stderr)

    resultado = {
        "vacancies": [v.to_dict() for v in all_vacancies],
        "errores": errores,
    }


    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()