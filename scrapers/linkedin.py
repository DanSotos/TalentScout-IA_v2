
import time
import random
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional
from scrapers.computrabajo import Vacancy


_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


class LinkedInScraper:
    """
    Scraper para LinkedIn Jobs (endpoint público /jobs/search).
    No requiere cuenta. Funciona mientras LinkedIn no exija JS/captcha.
    """

    BASE_URL   = "https://www.linkedin.com"
    SEARCH_URL = f"{BASE_URL}/jobs/search"

    def __init__(self):
        self.client = httpx.Client(
            timeout=25,
            follow_redirects=True,
        )

    def _headers(self) -> dict:
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        }

    def search(
        self,
        keywords: str,
        location: str = "Lima, Peru",
        limit: int = 10,
    ) -> List[Vacancy]:
        vacancies: List[Vacancy] = []
        start = 0        # LinkedIn pagina de 25 en 25

        while len(vacancies) < limit:
            params = {
                "keywords": keywords,
                "location": location,
                "start": start,
                "f_TPR": "r604800",   # últimos 7 días
                "sortBy": "DD",        # más recientes primero
            }
            print(f"   🌐 LinkedIn /jobs/search start={start}")
            try:
                resp = self.client.get(
                    self.SEARCH_URL,
                    params=params,
                    headers=self._headers(),
                )

                if resp.status_code in (429, 999):
                    print("   ⚠  LinkedIn rate-limit / anti-bot (429/999). "
                          "Espera y vuelve a intentar, o usa Playwright.")
                    break
                if resp.status_code != 200:
                    print(f"   ⚠  LinkedIn status {resp.status_code}")
                    break

                # LinkedIn puede redirigir a /login si no hay sesión
                if "/login" in str(resp.url) or "authwall" in str(resp.url):
                    print("   ⚠  LinkedIn requiere login para esta búsqueda.")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = self._find_cards(soup)

                if not cards:
                    print("   ℹ  LinkedIn: sin cards (posible bloqueo de JS)")
                    break

                print(f"   ✓  {len(cards)} ofertas encontradas")
                for card in cards:
                    if len(vacancies) >= limit:
                        break
                    v = self._parse_card(card)
                    if v:
                        vacancies.append(v)

                start += 25
                time.sleep(random.uniform(2.0, 4.0))

            except httpx.TimeoutException:
                print("   ⚠  Timeout en LinkedIn")
                break
            except Exception as e:
                print(f"   ⚠  Error LinkedIn: {e}")
                break

        return vacancies

    def _find_cards(self, soup: BeautifulSoup):
        """Prueba selectores conocidos de LinkedIn."""
        selectors = [
            "div.base-card",                         # layout clásico público
            "li.jobs-search__results-list > div",
            "div.job-search-card",
            "li[class*='result-card']",
            "ul.jobs-search__results-list > li",
        ]
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                return cards
        return []

    def _parse_card(self, card) -> Optional[Vacancy]:
        try:
            title_el   = card.select_one("h3.base-search-card__title") or card.select_one("h3")
            company_el = card.select_one("h4.base-search-card__subtitle") or card.select_one("h4")
            location_el = card.select_one("span.job-search-card__location")
            link_el    = card.select_one("a.base-card__full-link") or card.select_one("a")

            title    = title_el.get_text(strip=True)   if title_el   else "Sin título"
            company  = company_el.get_text(strip=True) if company_el else "Sin empresa"
            location = location_el.get_text(strip=True) if location_el else ""
            url      = link_el.get("href", "")         if link_el    else ""
            # Limpiar tracking params de LinkedIn
            url = url.split("?")[0] if url else ""
            job_id = url.rstrip("/").split("-")[-1] if url else "0"

            description = self._fetch_description(url)

            return Vacancy(
                id=f"li_{job_id}",
                title=title,
                company=company,
                location=location,
                description=description,
                requirements=[],
                salary="",
                url=url,
                source="linkedin",
            )
        except Exception as e:
            print(f"   ⚠  Error parseando card LinkedIn: {e}")
            return None

    def _fetch_description(self, url: str) -> str:
      
        if not url:
            return ""
        try:
            time.sleep(random.uniform(1.0, 2.0))
            resp = self.client.get(url, headers=self._headers())
            if resp.status_code != 200:
                print(f"   ⚠  Detalle LinkedIn status {resp.status_code} ({url})")
                return ""

            soup = BeautifulSoup(resp.text, "html.parser")
            box = soup.select_one('span[data-testid="expandable-text-box"]')
            if not box:
                print("   ℹ  Detalle LinkedIn: no se encontró expandable-text-box")
                return ""

            btn = box.select_one('[data-testid="expandable-text-button"]')
            if btn:
                btn.decompose()

            return box.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"   ⚠  Error obteniendo detalle LinkedIn ({url}): {e}")
            return ""