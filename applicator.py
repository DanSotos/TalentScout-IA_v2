"""
applicator.py - Módulo 5: Postulación supervisada con sesiones persistentes
Soporta LinkedIn (Easy Apply) y Computrabajo con cookies guardadas.
"""
import json
import time
import random
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import Optional

from scrapers.computrabajo import Vacancy
from config import LOGS_DIR, CV_DIR

RESULT_SENT      = "ENVIADA"
RESULT_POSTPONED = "POSPUESTA"
RESULT_SKIPPED   = "DESCARTADA"
RESULT_FALLBACK  = "FALLBACK_MANUAL"
RESULT_ERROR     = "ERROR"

SESSIONS_DIR = Path(__file__).parent / "data" / "sessions"


class SessionManager:
    """
    Guarda y carga cookies de sesión por portal.
    Primera vez: abre Chrome con perfil dedicado para login manual.
    Siguientes veces: carga cookies y navega ya autenticado.
    """

    PORTALS = {
        "linkedin":     "https://www.linkedin.com",
        "computrabajo": "https://www.computrabajo.com.pe",
    }

    def __init__(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def session_path(self, portal: str) -> Path:
        return SESSIONS_DIR / f"{portal}.json"

    def has_session(self, portal: str) -> bool:
        p = self.session_path(portal)
        return p.exists() and p.stat().st_size > 10

    def save_session(self, portal: str, cookies: list) -> None:
        self.session_path(portal).write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  ✅ Sesión guardada para {portal}")

    def load_session(self, portal: str) -> list:
        try:
            return json.loads(self.session_path(portal).read_text(encoding="utf-8"))
        except Exception:
            return []

    def delete_session(self, portal: str) -> None:
        p = self.session_path(portal)
        if p.exists():
            p.unlink()
            print(f"  🗑  Sesión eliminada para {portal}")

    @staticmethod
    def _get_chrome_profile_path() -> str:
        """Perfil dedicado solo para el agente — sin conflicto con Chrome abierto."""
        import os
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "chrome_profile")
        os.makedirs(base, exist_ok=True)
        return base

    @staticmethod
    def _launch_browser(p):
        """
        Lanza Chromium de Playwright para navegar con cookies.
        No usa perfil real — la sesión se maneja via cookies inyectadas.
        """
        browser = p.chromium.launch(headless=False)
        return browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="es-PE",
        )

    def do_manual_login(self, portal: str) -> list:
        """
        Abre Chrome con perfil dedicado para login manual.
        Las cookies se guardan y reutilizan en ejecuciones futuras.
        """
        from playwright.sync_api import sync_playwright

        chrome_profile = self._get_chrome_profile_path()

        print(f"\n  🔐 SESIÓN REQUERIDA — {portal.upper()}")
        print(f"  ✓  Perfil del agente: {chrome_profile}")
        print(f"  Se abrirá un Chrome en {self.PORTALS[portal]}")
        print(f"  → Iniciá sesión con usuario y contraseña (no uses 'Iniciar con Google')")
        input("\n  ENTER para abrir el navegador → ")

        cookies = []
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=chrome_profile,
                headless=False,
                channel="chrome",
                args=["--profile-directory=Default"],
                locale="es-PE",
                slow_mo=50,
            )
            page = context.new_page()
            page.goto(self.PORTALS[portal], wait_until="domcontentloaded", timeout=30_000)

            already_logged = (
                "feed" in page.url or
                "inicio" in page.url or
                ("linkedin" in portal and "/feed" in page.url) or
                ("computrabajo" in portal and "mi-cuenta" in page.url)
            )

            if already_logged:
                print("  ✅ Sesión activa detectada automáticamente.")
            else:
                print("  Por favor iniciá sesión en el navegador que se abrió.")
                input("  ✅ Cuando estés en el inicio/feed, presioná ENTER aquí → ")

            cookies = context.cookies()
            context.close()

        if cookies:
            self.save_session(portal, cookies)
        else:
            print("  ⚠  No se encontraron cookies. Intentá de nuevo.")
        return cookies


class SupervisedApplicator:

    def __init__(self, cv_path: Optional[Path] = None):
        self.cv_path = cv_path or self._find_cv()
        self.session_mgr = SessionManager()

    # ── Punto de entrada ──────────────────────────────────────────
    def process(self, vacancy: Vacancy, cv_text: str, decision) -> dict:
        self._print_summary(vacancy, decision)

        # Streamlit ya confirmó con el botón
        result = self._attempt_submission(vacancy, cv_text)

        self._log_result(vacancy, decision, result, cv_text)

        return result

    # ── Resumen XAI ───────────────────────────────────────────────
    def _print_summary(self, vacancy: Vacancy, decision) -> None:
        bar = "─" * 58
        print(f"\n┌{bar}┐")
        print(f"│  POSTULACIÓN PENDIENTE DE CONFIRMACIÓN")
        print(f"├{bar}┤")
        print(f"│  Puesto   : {vacancy.title}")
        print(f"│  Empresa  : {vacancy.company}")
        print(f"│  Ubicación: {vacancy.location or 'No especificada'}")
        print(f"│  Salario  : {vacancy.salary or 'No indicado'}")
        print(f"│  Fuente   : {vacancy.source.upper()}")
        print(f"│  URL      : {vacancy.url or 'No disponible'}")
        print(f"├{bar}┤")
        print(f"│  COMPATIBILIDAD : {decision.compatibility_level}  "
              f"(score: {decision.similarity_score:.2f})")
        print(f"│  EXPLICACIÓN XAI:")
        for line in self._wrap(decision.explanation, 54):
            print(f"│    {line}")
        print(f"└{bar}┘")

    # ── Confirmación ──────────────────────────────────────────────
    def _ask_confirmation(self, vacancy: Vacancy) -> str:
        print("\n  ¿Qué deseas hacer con esta postulación?")
        print("  [S] Confirmar y postular ahora")
        print("  [P] Posponer (guardar para después)")
        print("  [N] Descartar esta vacante")
        while True:
            raw = input("\n  Tu decisión [S/P/N]: ").strip().lower()
            if raw in ("s", "p", "n"):
                return raw
            print("  Por favor ingresa S, P o N.")

    # ── Despacho por portal ───────────────────────────────────────
    def _attempt_submission(self, vacancy: Vacancy, cv_text: str) -> dict:
        source = vacancy.source.lower()

        if source == "computrabajo" and vacancy.url:
            print("\n  → Iniciando postulación en Computrabajo...")
            ok, msg = self._submit_with_session("computrabajo", vacancy, self._submit_computrabajo)
            if ok:
                print(f"  ✅ {msg}")
                return {"status": RESULT_SENT, "message": msg}
            print(f"  ⚠  {msg}")
            return self._fallback_manual(vacancy)

        elif source == "linkedin" and vacancy.url:
            print("\n  → Iniciando postulación en LinkedIn...")
            ok, msg = self._submit_with_session("linkedin", vacancy, self._submit_linkedin)
            if ok:
                print(f"  ✅ {msg}")
                return {"status": RESULT_SENT, "message": msg}
            print(f"  ⚠  {msg}")
            return self._fallback_manual(vacancy)

        else:
            print(f"\n  ℹ  Envío automático no disponible para '{vacancy.source}'.")
            return self._fallback_manual(vacancy)

    # ── Wrapper de sesión ─────────────────────────────────────────
    def _submit_with_session(self, portal: str, vacancy: Vacancy, submit_fn) -> tuple:
        for attempt in range(2):
            if not self.session_mgr.has_session(portal):
                print(f"\n  ℹ  No hay sesión guardada para {portal.upper()}.")
                cookies = self.session_mgr.do_manual_login(portal)
                if not cookies:
                    return False, "No se pudo guardar la sesión."
            else:
                if attempt == 0:
                    print(f"  ✓  Sesión existente cargada para {portal.upper()}")
                cookies = self.session_mgr.load_session(portal)

            ok, msg = submit_fn(vacancy, cookies)

            if ok:
                return True, msg

            if any(k in msg.lower() for k in ("login", "sesión", "authwall", "expirada")):
                print(f"  ⚠  Sesión expirada. Solicitando nuevo login...")
                self.session_mgr.delete_session(portal)
                continue

            return False, msg

        return False, "No se pudo autenticar después de 2 intentos."

    # ── Envío Computrabajo ────────────────────────────────────────
    def _submit_computrabajo(self, vacancy: Vacancy, cookies: list) -> tuple:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            return False, "Playwright no instalado"

        try:
            with sync_playwright() as p:
                context = self.session_mgr._launch_browser(p)
                context.add_cookies(cookies)
                page = context.new_page()

                print(f"  🌐 {vacancy.url}")
                page.goto(vacancy.url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(random.uniform(1.5, 2.5))

                if "login" in page.url or "iniciar" in page.url:
                    context.close()
                    return False, "sesión expirada — login requerido"

                APPLY_SELECTORS = [
                    "a[data-testid='btn-apply']",
                    "button[data-testid='btn-apply']",
                    "a.btn_blue:has-text('Postularme')",
                    "a:has-text('Postularme')",
                    "button:has-text('Postularme')",
                    "a:has-text('Inscribirme')",
                    "button:has-text('Inscribirme')",
                ]
                apply_btn = None
                for sel in APPLY_SELECTORS:
                    try:
                        apply_btn = page.wait_for_selector(sel, timeout=4_000)
                        if apply_btn:
                            break
                    except PWTimeout:
                        continue

                if not apply_btn:
                    context.close()
                    return False, "Botón de postulación no encontrado"

                apply_btn.click()
                time.sleep(random.uniform(1.0, 2.0))

                CONFIRM_SELECTORS = [
                    "button:has-text('Confirmar')",
                    "button:has-text('Enviar')",
                    "button:has-text('Postular')",
                    "input[type='submit']",
                ]
                confirmed = False
                for sel in CONFIRM_SELECTORS:
                    try:
                        btn = page.wait_for_selector(sel, timeout=3_000)
                        if btn:
                            btn.click()
                            confirmed = True
                            break
                    except PWTimeout:
                        continue

                time.sleep(1.5)
                page_text = page.inner_text("body").lower()
                SUCCESS_TEXTS = ["postulación enviada", "te has postulado",
                                 "inscripción realizada", "application sent"]
                success = any(t in page_text for t in SUCCESS_TEXTS) or confirmed
                context.close()

                if success:
                    return True, f"Postulación enviada a {vacancy.company}"
                return False, "No se pudo confirmar el envío"

        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # ── Envío LinkedIn ────────────────────────────────────────────
    def _submit_linkedin(self, vacancy: Vacancy, cookies: list) -> tuple:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            return False, "Playwright no instalado"

        try:
            with sync_playwright() as p:
                context = self.session_mgr._launch_browser(p)
                context.add_cookies(cookies)
                page = context.new_page()

                print(f"  🌐 {vacancy.url}")
                page.goto(vacancy.url, wait_until="domcontentloaded", timeout=30_000)
                time.sleep(random.uniform(2.0, 3.0))

                if "authwall" in page.url or "/login" in page.url:
                    context.close()
                    return False, "sesión expirada — login requerido"

                # ── Buscar botón de postulación ───────────────────────────────
                # Acepta tanto "Solicitud sencilla" (Easy Apply) como "Solicitar"
                APPLY_SELECTORS = [
                    "button.jobs-apply-button:has-text('Solicitud sencilla')",
                    "button.jobs-apply-button:has-text('Easy Apply')",
                    "button.jobs-apply-button:has-text('Solicitar')",
                    "button.jobs-apply-button:has-text('Apply')",
                    "button[aria-label*='Solicitud sencilla']",
                    "button[aria-label*='Easy Apply']",
                    "button[aria-label*='Solicitar']",
                    "button[aria-label*='Apply']",
                    "button.jobs-apply-button",
                    ".jobs-apply-button",
                ]

                apply_btn = None
                for sel in APPLY_SELECTORS:
                    try:
                        btn = page.wait_for_selector(sel, timeout=8_000)
                        if btn:
                            apply_btn = btn
                            print(f"  ✓  Botón encontrado")
                            break
                    except PWTimeout:
                        continue

                if not apply_btn:
                    context.close()
                    return False, "Botón de postulación no encontrado en LinkedIn"

                apply_btn.click()
                time.sleep(random.uniform(1.5, 2.0))

                # ── Detectar modal de Easy Apply ──────────────────────────────
                MODAL_SELECTORS = [
                    "div.jobs-easy-apply-modal",
                    "div[data-test-modal]",
                    "[aria-label*='Solicitud']",
                    "[aria-label*='Apply']",
                ]
                has_modal = False
                for sel in MODAL_SELECTORS:
                    try:
                        page.wait_for_selector(sel, timeout=4_000)
                        has_modal = True
                        break
                    except PWTimeout:
                        continue

                if has_modal:
                    # Buscar botón de envío directo
                    SUBMIT_SELECTORS = [
                        "button[aria-label='Enviar solicitud']",
                        "button[aria-label='Submit application']",
                        "button[aria-label*='Enviar']",
                        "button[aria-label*='Submit']",
                        "button:has-text('Enviar solicitud')",
                        "button:has-text('Submit application')",
                        "button:has-text('Enviar')",
                        "footer button[data-easy-apply-next-button]",
                    ]
                    submit_btn = None
                    for sel in SUBMIT_SELECTORS:
                        try:
                            submit_btn = page.wait_for_selector(sel, timeout=2_000)
                            if submit_btn:
                                break
                        except PWTimeout:
                            continue

                    if submit_btn:
                        submit_btn.click()
                        time.sleep(1.5)
                        context.close()
                        return True, f"Easy Apply enviado a {vacancy.company}"
                    else:
                        # Formulario con campos extra → el usuario lo completa
                        print("\n  📋 El formulario tiene campos adicionales.")
                        print("Formulario abierto.")
                        print("Completa manualmente la solicitud.")

                        return True, "Formulario abierto para completar manualmente"
        

            
                time.sleep(1.5)

                if "linkedin" not in page.url:
                    print("\n📋 Se abrió la página del empleador.")
                    print("Completa la postulación manualmente.")

                    return True, "Se abrió el sitio del empleador"

                context.close()
                return False, "No se pudo completar el flujo de postulación"

        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # ── Fallback manual ───────────────────────────────────────────
    def _fallback_manual(self, vacancy: Vacancy) -> dict:
        print("\n  📋 FALLBACK MANUAL ACTIVADO")
        if vacancy.url:
            webbrowser.open(vacancy.url)
            print(f"  → Abierto: {vacancy.url}")
        else:
            print("  ⚠  Sin URL disponible.")
        # La confirmación de "ya postulé manualmente" la da el usuario
        # desde la UI de Streamlit (botón), no desde esta consola oculta.
        return {"status": RESULT_FALLBACK, "message": "Derivado a postulación manual"}

    # ── Posponer ──────────────────────────────────────────────────
    def _postpone(self, vacancy: Vacancy) -> dict:
        postponed_file = LOGS_DIR / "postponed.jsonl"
        entry = {"timestamp": datetime.now().isoformat(), "vacancy": vacancy.to_dict()}
        with postponed_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"  📌 Guardada en {postponed_file.name}")
        return {"status": RESULT_POSTPONED, "message": "Guardada para revisión posterior"}

    # ── Descartar ─────────────────────────────────────────────────
    def _skip(self, vacancy: Vacancy) -> dict:
        print("  ❌ Vacante descartada.")
        return {"status": RESULT_SKIPPED, "message": "Descartada manualmente"}

    # ── Log ───────────────────────────────────────────────────────
    def _log_result(self, vacancy: Vacancy, decision, result: dict, cv_text: str) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        status = result.get("status", "DESCONOCIDO")
        log_file = LOGS_DIR / f"application_{vacancy.id}_{ts}_{status}.txt"
        cover_letter = self._generate_cover_letter(vacancy, cv_text)
        content = (
            f"=== POSTULACIÓN ===\n"
            f"Fecha          : {datetime.now().isoformat()}\n"
            f"Puesto         : {vacancy.title}\n"
            f"Empresa        : {vacancy.company}\n"
            f"URL            : {vacancy.url}\n"
            f"Fuente         : {vacancy.source}\n"
            f"Resultado      : {status}\n"
            f"Detalle        : {result.get('message', '')}\n"
            f"Compatibilidad : {decision.compatibility_level} "
            f"(score: {decision.similarity_score:.4f})\n"
            f"XAI            : {decision.explanation}\n\n"
            f"=== CARTA DE PRESENTACIÓN ===\n{cover_letter}\n"
        )
        log_file.write_text(content, encoding="utf-8")

    # ── Helpers ───────────────────────────────────────────────────
    def _generate_cover_letter(self, vacancy: Vacancy, cv_text: str) -> str:
        lines = cv_text.strip().splitlines()
        name = lines[0].strip() if lines else "Candidato"
        date = datetime.now().strftime("%d/%m/%Y")
        reqs = ", ".join(vacancy.requirements[:3]) if vacancy.requirements else "las requeridas"
        return (
            f"Estimado equipo de {vacancy.company},\n\n"
            f"Me dirijo a ustedes con gran interés por la posición de {vacancy.title}.\n"
            f"Mi perfil profesional se alinea con los requisitos del puesto, "
            f"especialmente en: {reqs}.\n\n"
            f"Quedo a su disposición para una entrevista.\n\n"
            f"Atentamente,\n{name}\n{date}"
        )

    def _find_cv(self) -> Optional[Path]:
        if CV_DIR.exists():
            pdfs = list(CV_DIR.glob("*.pdf"))
            return pdfs[0] if pdfs else None
        return None

    @staticmethod
    def _wrap(text: str, width: int) -> list:
        words = text.split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 <= width:
                current += (" " if current else "") + w
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines or [""]


class Applicator(SupervisedApplicator):
    """Alias de compatibilidad."""
    def prepare_application(self, vacancy: Vacancy, cv_text: str) -> dict:
        cover_letter = self._generate_cover_letter(vacancy, cv_text)
        log_file = LOGS_DIR / f"application_{vacancy.id}_prepared.txt"
        log_file.write_text(cover_letter, encoding="utf-8")
        print(f"   → Preparada: {vacancy.title} @ {vacancy.company}")
        return {"vacancy": vacancy.to_dict(), "cover_letter": cover_letter}