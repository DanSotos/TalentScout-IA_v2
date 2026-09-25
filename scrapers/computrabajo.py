"""
scrapers/computrabajo.py - Scraper real para Computrabajo.com.pe
Usa Playwright para ejecutar JavaScript como un browser real.
"""
import time
import random
from typing import List, Optional
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright


@dataclass
class Vacancy:
    id: str
    title: str
    company: str
    location: str
    description: str
    requirements: List[str] = field(default_factory=list)
    salary: str = ""
    url: str = ""
    source: str = "computrabajo"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
            "requirements": self.requirements,
            "salary": self.salary,
            "url": self.url,
            "source": self.source,
        }

    def get_full_text(self) -> str:
        reqs = " ".join(self.requirements)
        return f"{self.title}. {self.company}. {self.description}. {reqs}"

    def get_signal_text(self) -> str:
        """
        Texto de "alta señal": solo título + requisitos/skills.

        Se usa con más peso que get_full_text() en el cálculo de
        similitud porque es lo que realmente distingue una carrera de
        otra. La descripción completa (funciones, beneficios, "ingreso
        a planilla con todos los beneficios de ley", etc.) es casi
        idéntica entre avisos de rubros totalmente distintos — mete
        ruido, no señal, y es la razón por la que hoy salen ALTA
        vacantes de otra carrera.
        """
        reqs = " ".join(self.requirements)
        return f"{self.title}. {reqs}".strip()


class CompuTrabajoScraper:

    BASE_URL = "https://www.computrabajo.com.pe"

    def search(self, keywords: str, location: str = "Lima", limit: int = 10) -> List[Vacancy]:
        slug = keywords.strip().lower().replace(" ", "-")
        loc_map = {"lima": "lima", "arequipa": "arequipa", "trujillo": "trujillo"}
        loc_slug = loc_map.get(location.lower())
        if loc_slug:
            url = f"{self.BASE_URL}/trabajo-de-{slug}-en-{loc_slug}"
        else:
            url = f"{self.BASE_URL}/trabajo-de-{slug}"

        vacancies: List[Vacancy] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-PE",
            )
            page = context.new_page()
            page_num = 1

            while len(vacancies) < limit:
                full_url = url if page_num == 1 else f"{url}?p={page_num}"
                print(f"   🌐 Playwright GET {full_url}")

                try:
                    page.goto(full_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_selector("article", timeout=15000)
                except Exception:
                    print(f"   ⚠  Timeout esperando cards en página {page_num}")
                    break

                cards = page.query_selector_all("article")
                if not cards:
                    print(f"   ℹ  Sin cards en página {page_num}")
                    break

                print(f"   ✓  Página {page_num}: {len(cards)} cards")

                for card in cards:
                    if len(vacancies) >= limit:
                        break
                    v = self._parse_card(card)
                    if v:
                        vacancies.append(v)

                page_num += 1
                time.sleep(random.uniform(1.5, 3.0))

            browser.close()

        return vacancies

    def _parse_card(self, card) -> Optional[Vacancy]:
        try:
            title_el    = card.query_selector("h2 a")
            company_el  = card.query_selector("a[offer-grid-article-company-url]")
            location_el = card.query_selector("p.fs16 span.mr10")
            salary_el = card.query_selector("div.fs13 span.dIB")

            title    = title_el.inner_text().strip()    if title_el    else "Sin título"
            href     = title_el.get_attribute("href")   if title_el    else ""
            url      = (self.BASE_URL + href) if href and href.startswith("/") else href or ""
            company  = company_el.inner_text().strip()  if company_el  else "Sin empresa"
            location = location_el.inner_text().strip() if location_el else ""
            salary    = salary_el.evaluate("el => el.innerText").strip() if salary_el else ""
            job_id   = url.rstrip("/").split("-")[-1].replace(".html", "") if url else "0"

            return Vacancy(
                id=f"ct_{job_id}",
                title=title,
                company=company,
                location=location,
                description="",
                requirements=[],
                salary=salary,
                url=url,
                source="computrabajo",
            )
        except Exception as e:
            print(f"   ⚠  Error parseando card: {e}")
            return None