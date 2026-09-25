import streamlit as st
from pypdf import PdfReader
import sqlite3
import json
import subprocess
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime

# Importaciones de tu backend real
from models.sentence_bert import SentenceBERTProcessor
from scrapers.computrabajo import Vacancy  # solo para reconstruir objetos desde el JSON del worker
from semantic_filter import SemanticFilter
from decision_maker import DecisionMaker
from utils.dedup import deduplicate_vacancies
from utils.cv_parser import extract_career_from_cv

WORKER_PATH = Path(__file__).parent / "apply_worker.py"

# --- CONFIGURACIÓN DE LA PLATAFORMA OFICIAL ---
st.set_page_config(page_title="TalentScout IA - Dashboard", page_icon="💼", layout="wide")

# --- FUNCIONES DE LA BASE DE DATOS (SQLITE) ---
def conectar_db():
    conn = sqlite3.connect("historial_postulaciones.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS postulaciones (
            id TEXT PRIMARY KEY,
            puesto TEXT,
            empresa TEXT,
            url TEXT,
            similitud REAL,
            nivel TEXT,
            fecha TEXT,
            estado TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metricas_tiempo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            n_vacantes_solicitadas INTEGER,
            n_vacantes_encontradas INTEGER,
            n_vacantes_filtradas INTEGER,
            t_embedding_cv REAL,
            t_busqueda_scraping REAL,
            t_filtrado_clasificacion REAL,
            t_pipeline_total REAL,
            cv_nombre TEXT,
            cv_hash TEXT
        )
    """)
    # Migración para bases de datos creadas antes de agregar cv_nombre/cv_hash.
    # Si las columnas ya existen, sqlite3 lanza OperationalError y se ignora.
    for columna, tipo in [("cv_nombre", "TEXT"), ("cv_hash", "TEXT")]:
        try:
            cursor.execute(f"ALTER TABLE metricas_tiempo ADD COLUMN {columna} {tipo}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    return conn

def guardar_en_historial(id_vacante, puesto, empresa, url, similitud, nivel, estado):
    conn = conectar_db()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO postulaciones (id, puesto, empresa, url, similitud, nivel, fecha, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (id_vacante, puesto, empresa, url, similitud, nivel, fecha_actual, estado))
        conn.commit()
    except Exception as e:
        st.error(f"Error al guardar en DB: {e}")
    finally:
        conn.close()

def obtener_historial():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT puesto, empresa, nivel, similitud, fecha, estado, url FROM postulaciones ORDER BY fecha DESC")
    datos = cursor.fetchall()
    conn.close()
    return datos


def guardar_metricas_tiempo(n_solicitadas, n_encontradas, n_filtradas,
                             t_embedding, t_busqueda, t_filtrado, t_total,
                             cv_nombre="", cv_hash=""):
    """
    Guarda el desglose de tiempos de UNA corrida del pipeline automático
    (carga+embedding del CV, scraping, filtrado+clasificación) para que
    puedas acumular varias corridas y reportar un promedio en el artículo,
    en vez de un solo número aislado.

    cv_nombre/cv_hash identifican con qué currículum se hizo la corrida,
    para poder distinguir el experimento principal de pruebas con otros CVs.
    """
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO metricas_tiempo
        (fecha, n_vacantes_solicitadas, n_vacantes_encontradas, n_vacantes_filtradas,
         t_embedding_cv, t_busqueda_scraping, t_filtrado_clasificacion, t_pipeline_total,
         cv_nombre, cv_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        n_solicitadas, n_encontradas, n_filtradas,
        t_embedding, t_busqueda, t_filtrado, t_total,
        cv_nombre, cv_hash,
    ))
    conn.commit()
    conn.close()


def obtener_metricas_tiempo():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fecha, n_vacantes_solicitadas, n_vacantes_encontradas, n_vacantes_filtradas,
               t_embedding_cv, t_busqueda_scraping, t_filtrado_clasificacion, t_pipeline_total,
               cv_nombre, cv_hash
        FROM metricas_tiempo ORDER BY fecha DESC
    """)
    datos = cursor.fetchall()
    conn.close()
    return datos


def _env_utf8() -> dict:
    """
    En Windows, los procesos hijos lanzados con subprocess heredan por
    defecto la codificación de la consola (cp1252/'charmap'), que no
    puede representar emojis como 🌐 o ✓ usados en los print() de los
    scrapers y de applicator.py. Esto fuerza al proceso hijo a usar
    UTF-8 para stdout/stderr, evitando UnicodeEncodeError.
    """
    import os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


SEARCH_WORKER_PATH = Path(__file__).parent / "search_worker.py"


def _extraer_json_de_stdout(stdout: str) -> dict:
    """
    Los scrapers reales usan print() normal para sus mensajes de progreso
    (🌐, ✓, ⚠), que terminan mezclados en stdout junto con la línea JSON
    final. En vez de asumir "la última línea es el JSON", se recorren las
    líneas de abajo hacia arriba y se devuelve la primera que sea JSON
    válido. Esto es más robusto que asumir un formato exacto de salida.
    """
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


def buscar_vacantes_subprocess(keywords: str, location: str, limit: int) -> dict:
    """
    Reemplaza la llamada directa a los scrapers (CompuTrabajoScraper,
    LinkedInScraper, IndeedScraper) dentro de app.py. Los ejecuta en
    search_worker.py, en un proceso de Python aparte, evitando el
    NotImplementedError de Playwright sync_api dentro del event loop
    de Streamlit.
    Devuelve {"vacancies": [...], "errores": {...}}.
    Si algo sale mal a nivel de proceso (no a nivel de un scraper
    puntual), devuelve {"vacancies": [], "errores": {"_proceso": "..."}}.
    """
    payload = {"keywords": keywords, "location": location, "limit": limit}

    proc = subprocess.run(
        [sys.executable, str(SEARCH_WORKER_PATH)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,  # el scraping puede tardar 45-75s por portal; dar margen
        env=_env_utf8(),
    )

    if proc.returncode != 0:
        return {"vacancies": [], "errores": {"_proceso": proc.stderr[-800:] if proc.stderr else "error desconocido"}}

    resultado = _extraer_json_de_stdout(proc.stdout)
    if not resultado:
        return {"vacancies": [], "errores": {"_proceso": "No se pudo interpretar la respuesta del worker"}}

    return resultado


# --- NUEVA FUNCIÓN: ejecuta la postulación en proceso aislado ────────────
def postular_con_agente_subprocess(vacancy, cv_text: str, decision) -> dict:
    """
    Reemplaza la llamada directa a SupervisedApplicator().process(...).
    Lanza apply_worker.py como proceso de Python independiente, le pasa
    los datos por stdin en JSON, y lee el resultado por stdout.
    Esto evita el NotImplementedError de Playwright sync_api dentro
    del event loop de Streamlit.
    """
    payload = {
        "vacancy": vacancy.to_dict(),
        "cv_text": cv_text,
        "decision": {
            "compatibility_level": decision.compatibility_level,
            "similarity_score": decision.similarity_score,
            "explanation": decision.explanation,
        },
    }

    proc = subprocess.run(
        [sys.executable, str(WORKER_PATH)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=_env_utf8(),
    )

    if proc.returncode != 0:
        return {"status": "ERROR", "message": proc.stderr[-800:] if proc.stderr else "Error desconocido"}

    lines = proc.stdout.strip().splitlines()
    result_line = lines[-1] if lines else "{}"
    try:
        return json.loads(result_line)
    except json.JSONDecodeError:
        return {"status": "ERROR", "message": "Respuesta del worker no interpretable"}


# --- INTERFAZ GRÁFICA PRO (PANELES / TABS) ---
st.title("💼 TalentScout IA")
st.caption("Plataforma Inteligente de Automatización y Análisis de Empleo")

tab_buscar, tab_historial = st.tabs(["🔍 Panel de Búsqueda", "📋 Mi Historial Oficial"])

# --- PESTAÑA 1: PANEL DE BÚSQUEDA ---
with tab_buscar:
    if "decisions" not in st.session_state:
        st.session_state.decisions = None
    if "all_vacancies_len" not in st.session_state:
        st.session_state.all_vacancies_len = 0

    col_inputs_left, col_inputs_right = st.columns([1, 1])

    with col_inputs_left:
        st.markdown("### 📂 Carga de Documento")
        uploaded_file = st.file_uploader("Arrastra tu CV en formato PDF", type="pdf")

    # Leemos el CV y detectamos el área ANTES de dibujar los campos de la derecha,
    # solo para poder mostrarla como referencia (no se usa como término de búsqueda).
    cv_text = None
    carrera_sugerida = ""
    if uploaded_file is not None:
        reader = PdfReader(uploaded_file)
        cv_text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
        cv_hash = hashlib.sha256(cv_text.encode("utf-8")).hexdigest()[:12]
        carrera_sugerida = extract_career_from_cv(cv_text)

    with col_inputs_right:
        st.markdown("### ⚙️ Configuración del Agente")
        if carrera_sugerida:
            st.caption(f"📌 Área detectada del CV: **{carrera_sugerida}**")
        elif uploaded_file is None:
            st.caption("📌 Área detectada del CV: _(sube tu CV para detectarla)_")
        keywords = st.text_input(
            "Cargo o preferencia laboral (opcional):",
            value="",
            placeholder="Ej: investigador en biología molecular, analista de datos junior...",
            help="Opcional. El área (arriba) siempre se usa para buscar y filtrar por rubro. "
                 "Si además escribes un cargo puntual, se usa como señal adicional para "
                 "afinar el ranking de las vacantes dentro de tu área.",
        )
        location = st.text_input("Ciudad / País:", value="")
        limit = st.number_input("Cantidad de ofertas a evaluar:", min_value=3, max_value=60, value=15, step=3)

    st.write("---")

    if uploaded_file is not None:
        st.success(f"✓ Currículum analizado correctamente en memoria.")

        carrera = st.text_input(
            "Área profesional (detectada automáticamente):",
            value=carrera_sugerida,
            help=(
                "Extraído automáticamente del CV. Se usa para descartar vacantes de un rubro "
                "completamente distinto al tuyo, aunque coincidan por palabras clave. "
                "Verificar si corresponde a tu área profesional."
            ),
        )

        # El área es obligatoria (se detecta sola del CV) y siempre es la que
        # se usa para buscar en los portales. El cargo es opcional: si se
        # escribe, se usa como una SEGUNDA señal de matching que afina el
        # ranking dentro de esa misma área (ver semantic_filter.py).
        if not keywords.strip():
            st.caption(f"ℹ️ No escribiste un cargo específico: se buscará y clasificará usando solo el área **{carrera}**.")
        else:
            st.caption(f"ℹ️ Se buscará por el área **{carrera}**, y el ranking se afinará según el cargo que escribiste.")

        if st.button("🚀 Ejecutar Agente de Inteligencia Artificial", disabled=not carrera.strip()):
            status_bar = st.status("Analizando mercado laboral...", expanded=True)
            with status_bar:
                t_pipeline_inicio = time.perf_counter()

                # ── Fase 1: Embedding del CV (y del cargo, si existe) ──
                st.write("Generando vectores semánticos con Sentence-BERT...")
                t0 = time.perf_counter()
                processor = SentenceBERTProcessor()
                processor.load_model()
                cv_embedding = processor.generate_cv_embedding(cv_text)
                cargo_embedding = (
                    processor.generate_embedding(keywords.strip()) if keywords.strip() else None
                )
                t_embedding = time.perf_counter() - t0

                # ── Fase 2: Búsqueda / scraping (proceso aparte) ────────
                st.write("Extrayendo ofertas en tiempo real con Playwright...")
                t0 = time.perf_counter()
                resultado_busqueda = buscar_vacantes_subprocess(carrera, location, limit)
                t_busqueda = time.perf_counter() - t0

                for nombre_scraper, err in resultado_busqueda.get("errores", {}).items():
                    st.write(f"⚠ Error en {nombre_scraper}: {err}")

                all_vacancies_raw = [Vacancy(**v) for v in resultado_busqueda.get("vacancies", [])]
                all_vacancies = deduplicate_vacancies(all_vacancies_raw)
                n_duplicados = len(all_vacancies_raw) - len(all_vacancies)
                if n_duplicados > 0:
                    st.write(f"ℹ️ Se descartaron {n_duplicados} vacante(s) duplicada(s).")

                if all_vacancies:
                    # ── Fase 3: Filtrado semántico + clasificación ──────
                    t0 = time.perf_counter()
                    semantic_filter = SemanticFilter(processor)
                    filtered = semantic_filter.filter_vacancies(
                        cv_embedding, all_vacancies,
                        declared_career=carrera,
                        cargo_embedding=cargo_embedding,
                    )

                    decision_maker = DecisionMaker(processor)
                    st.session_state.decisions = []
                    for vacancy, score in filtered:
                        decision = decision_maker.make_decision(cv_text, vacancy, score)
                        st.session_state.decisions.append((vacancy, decision))
                    t_filtrado = time.perf_counter() - t0

                    t_pipeline_total = time.perf_counter() - t_pipeline_inicio

                    guardar_metricas_tiempo(
                        n_solicitadas=limit,
                        n_encontradas=len(all_vacancies),
                        n_filtradas=len(filtered),
                        t_embedding=t_embedding,
                        t_busqueda=t_busqueda,
                        t_filtrado=t_filtrado,
                        t_total=t_pipeline_total,
                        cv_nombre=uploaded_file.name,
                        cv_hash=cv_hash,
                    )

                    st.session_state.ultima_metrica = {
                        "embedding": t_embedding,
                        "busqueda": t_busqueda,
                        "filtrado": t_filtrado,
                        "total": t_pipeline_total,
                    }

                    status_bar.update(label="Análisis completado con éxito", state="complete", expanded=False)
                else:
                    st.error("No se encontraron ofertas en este momento.")

        # Mostrar el desglose de tiempo de la última corrida (para el artículo)
        if st.session_state.get("ultima_metrica"):
            m = st.session_state.ultima_metrica
            st.markdown("#### ⏱️ Tiempo del pipeline automático (última ejecución)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Embedding CV", f"{m['embedding']:.2f} s")
            c2.metric("Búsqueda/scraping", f"{m['busqueda']:.2f} s")
            c3.metric("Filtrado+clasificación", f"{m['filtrado']:.2f} s")
            c4.metric("Total pipeline", f"{m['total']:.2f} s")
            st.caption(
                "No incluye el tiempo de revisión/confirmación humana de cada "
                "vacante ni el envío de postulaciones — solo el tramo "
                "completamente automatizado del agente."
            )

        # Mostrar resultados de la búsqueda
        if st.session_state.decisions is not None:
            st.markdown("## 📊 Resultados del Análisis de Compatibilidad")

            for vacancy, decision in st.session_state.decisions:
                color = {"ALTA": "🟢", "MEDIA": "🟡", "BAJA": "🔴"}.get(decision.compatibility_level, "⚪")

                with st.expander(f"{color} {vacancy.title} — {vacancy.company}"):
                    st.write(f"**🔗 Enlace original:** [Ver Vacante]({vacancy.url})")
                    st.write(f"**🎯 Compatibilidad Semántica:** `{decision.similarity_score:.2f}` ({decision.compatibility_level})")
                    st.info(f"**Evaluación de la IA:** {decision.explanation}")

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("⚡ Postular con el Agente", key=f"real_apply_{vacancy.id}"):
                            with st.spinner("Playwright abriendo navegador y rellenando datos..."):
                                result = postular_con_agente_subprocess(vacancy, cv_text, decision)

                                estado = result.get("status", "ERROR")
                                if estado == "ENVIADA":
                                    guardar_en_historial(
                                        vacancy.id, vacancy.title, vacancy.company, vacancy.url,
                                        decision.similarity_score, decision.compatibility_level,
                                        "POSTULADO ✅",
                                    )
                                    st.toast(f"🎉 ¡Postulación completada con éxito en la web para {vacancy.company}!")
                                elif estado == "FALLBACK_MANUAL":
                                    guardar_en_historial(
                                        vacancy.id, vacancy.title, vacancy.company, vacancy.url,
                                        decision.similarity_score, decision.compatibility_level,
                                        "FALLBACK MANUAL 📋",
                                    )
                                    st.warning(
                                        "El envío automático no fue posible (protección anti-bot de la "
                                        "plataforma). Se abrió la vacante en tu navegador para completarla "
                                        "manualmente."
                                    )
                                else:
                                    st.error(f"No se pudo completar la postulación: {result.get('message', 'sin detalle')}")

                    with btn_col2:
                        if st.button("💾 Guardar en Historial Local", key=f"real_save_{vacancy.id}"):
                            guardar_en_historial(vacancy.id, vacancy.title, vacancy.company, vacancy.url, decision.similarity_score, decision.compatibility_level, "GUARDADO 📌")
                            st.toast(f"💾 Guardado de forma permanente en tu historial.")

# --- PESTAÑA 2: MI HISTORIAL OFICIAL ---
with tab_historial:
    st.markdown("## 📋 Registro Histórico de Vacantes")
    st.write("Aquí se guardan las vacantes filtradas en cada sesion.")

    registros = obtener_historial()

    if registros:
        tabla_datos = []
        for reg in registros:
            tabla_datos.append({
                "Puesto": reg[0],
                "Empresa": reg[1],
                "Nivel": reg[2],
                "Compatibilidad": f"{reg[3]:.2f}",
                "Fecha de Registro": reg[4],
                "Estado Actual": reg[5],
                "Link": reg[6]
            })
        st.dataframe(tabla_datos, use_container_width=True)
    else:
        st.info("Aún no tienes vacantes guardadas en tu historial permanente.")

    st.markdown("---")
    st.markdown("## ⏱️ Métricas de tiempo del pipeline (todas las corridas)")
    st.caption(
        "Cada fila es una ejecución completa del botón "
        "'Ejecutar Agente de Inteligencia Artificial'. Útil para reportar "
        "un promedio en el artículo en vez de un solo dato aislado."
    )

    metricas = obtener_metricas_tiempo()
    if metricas:
        tabla_metricas = []
        for m in metricas:
            tabla_metricas.append({
                "Fecha": m[0],
                "Vacantes solicitadas": m[1],
                "Vacantes encontradas": m[2],
                "Vacantes filtradas": m[3],
                "Embedding CV (s)": f"{m[4]:.2f}",
                "Búsqueda/scraping (s)": f"{m[5]:.2f}",
                "Filtrado+clasificación (s)": f"{m[6]:.2f}",
                "Total pipeline (s)": f"{m[7]:.2f}",
                "CV": m[8] or "—",
                "Hash CV": m[9] or "—",
            })
        st.dataframe(tabla_metricas, use_container_width=True)

        n = len(metricas)
        promedio_total = sum(m[7] for m in metricas) / n
        promedio_busqueda = sum(m[5] for m in metricas) / n
        st.write(
            f"**Promedio sobre {n} corrida(s):** "
            f"pipeline total = {promedio_total:.2f} s · "
            f"búsqueda/scraping = {promedio_busqueda:.2f} s"
        )
        if n < 3:
            st.warning(
                "Tienes menos de 3 corridas registradas. Para citar un "
                "promedio en el artículo, conviene acumular al menos "
                "3-5 ejecuciones completas con condiciones similares "
                "(mismo CV, mismo número de vacantes)."
            )
    else:
        st.info("Aún no hay corridas registradas. Ejecuta el agente al menos una vez desde el Panel de Búsqueda.")