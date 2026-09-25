
import time
import random
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional
from scrapers.computrabajo import Vacancy


class IndeedScraper:
    """
    Scraper para Indeed Perú.
    Indeed suele necesitar cookies de sesión (visita previa al home).
    """

    BASE_URL   = "https://pe.indeed.com"
    SEARCH_URL = f"{BASE_URL}/jobs"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self):
        self.client = httpx.Client(
            headers=self.HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        self._warmed_up = False

    def _warmup(self):
        if self._warmed_up:
            return
        try:
            self.client.get(self.BASE_URL)
            time.sleep(random.uniform(1.5, 2.5))
            self._warmed_up = True
        except Exception:
            pass

    def search(
        self,
        keywords: str,
        location: str = "Lima",
        limit: int = 10,
    ) -> List[Vacancy]:
        self._warmup()
        vacancies: List[Vacancy] = []
        start = 0  # Indeed pagina de 10 en 10

        while len(vacancies) < limit:
            params = {
                "q": keywords,
                "l": location,
                "start": start,
                "sort": "date",
            }
            print(f"   🌐 Indeed /jobs start={start}")
            try:
                resp = self.client.get(
                    self.SEARCH_URL,
                    params=params,
                    headers={**self.HEADERS, "Referer": self.BASE_URL + "/"},
                )

                if resp.status_code == 403:
                    print("   ⚠  Indeed bloqueó (403 / Cloudflare). "
                          "Intenta con Playwright + stealth plugin.")
                    break
                if resp.status_code != 200:
                    print(f"   ⚠  Indeed status {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = self._find_cards(soup)

                if not cards:
                    print("   ℹ  Indeed: sin cards en esta página")
                    break

                print(f"   ✓  {len(cards)} resultados en start={start}")
                for card in cards:
                    if len(vacancies) >= limit:
                        break
                    v = self._parse_card(card)
                    if v:
                        vacancies.append(v)

                start += 10
                time.sleep(random.uniform(2.0, 4.0))

            except httpx.TimeoutException:
                print("   ⚠  Timeout en Indeed")
                break
            except Exception as e:
                print(f"   ⚠  Error Indeed: {e}")
                break

        return vacancies

    def _find_cards(self, soup: BeautifulSoup):
        selectors = [
            "div.job_seen_beacon",                # 2024 layout
            "div[class*='jobsearch-SerpJobCard']",
            "div.result",
            "li[class*='css-']",
            "td.resultContent",
        ]
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                return cards
        return []

    def _parse_card(self, card) -> Optional[Vacancy]:
        try:
            title_el = (
                card.select_one("h2.jobTitle a span")
                or card.select_one("h2 a")
                or card.select_one("[class*='jobTitle']")
            )
            company_el = (
                card.select_one("span[data-testid='company-name']")
                or card.select_one("span.companyName")
                or card.select_one("[class*='company']")
            )
            location_el = (
                card.select_one("div[data-testid='text-location']")
                or card.select_one("div.companyLocation")
            )
            salary_el = card.select_one("div[class*='salary']") or card.select_one("[class*='salary']")
            link_el   = card.select_one("h2 a") or card.select_one("a[data-jk]")

            title    = title_el.get_text(strip=True)    if title_el    else "Sin título"
            company  = company_el.get_text(strip=True)  if company_el  else "Sin empresa"
            location = location_el.get_text(strip=True) if location_el else ""
            salary   = salary_el.get_text(strip=True)   if salary_el   else ""

            href = link_el.get("href", "") if link_el else ""
            url  = (self.BASE_URL + href) if href.startswith("/") else href
            job_id = link_el.get("data-jk") or url.split("jk=")[-1].split("&")[0] if url else "0"

            snippet_el = card.select_one("div[class*='summary']") or card.select_one("ul")
            description = snippet_el.get_text(separator=" ", strip=True) if snippet_el else ""

            return Vacancy(
                id=f"in_{job_id}",
                title=title,
                company=company,
                location=location,
                description=description,
                requirements=[],
                salary=salary,
                url=url,
                source="indeed",
            )
        except Exception as e:
            print(f"   ⚠  Error parseando card Indeed: {e}")
            return None