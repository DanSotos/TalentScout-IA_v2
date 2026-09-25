# TalentScout-IA_v2

> Agente Autónomo Basado en Inteligencia Artificial para la Selección y Postulación Inteligente a Convocatorias Laborales.

TalentScout-IA es un sistema inteligente que automatiza el proceso de búsqueda, evaluación y postulación a ofertas laborales mediante técnicas de Inteligencia Artificial, Procesamiento de Lenguaje Natural (NLP) y automatización web.

El sistema analiza el perfil profesional del usuario, identifica oportunidades laborales compatibles utilizando embeddings semánticos y permite automatizar el proceso de postulación bajo un esquema de autonomía supervisada.

---

# Características

- Análisis automático del CV.
- Búsqueda inteligente de vacantes en múltiples portales (Computrabajo, LinkedIn, Indeed, Bumeran).
- Filtrado por cargo/puesto deseado, para mayor precisión en los resultados.
- Deduplicación de vacantes entre portales.
- Matching semántico mediante Sentence-BERT, con umbrales de similitud calibrables.
- Toma de decisiones basada en IA, con explicaciones XAI (skills coincidentes / faltantes).
- Generación automática de cartas de presentación.
- Automatización de postulaciones con Playwright, bajo supervisión del usuario.
- Retroalimentación adaptativa: historial de corridas y detección de brechas de habilidades (skill gaps).

---

# Tecnologías utilizadas

- Python 3.11
- Streamlit
- Playwright
- BeautifulSoup
- Sentence Transformers (Sentence-BERT)
- SQLite
- Pandas / NumPy / scikit-learn
- pdfplumber / PyPDF2

---

# Estructura del proyecto

```text
TalentScout-IA_v2/
│
├── data/                       # Datos utilizados por el sistema
├── models/                     # Modelos y recursos de IA (Sentence-BERT)
├── scrapers/                   # Scrapers de portales de empleo
├── utils/                      # Funciones auxiliares
│   ├── career_filter.py        # Filtrado de vacantes por cargo/puesto deseado
│   ├── cv_parser.py            # Extracción de datos del CV
│   └── dedup.py                # Deduplicación de vacantes entre portales
│
├── app.py                      # Interfaz gráfica en Streamlit
├── main.py                     # Punto de entrada desde consola
├── applicator.py               # Gestión de postulaciones y generación de cartas
├── apply_worker.py             # Automatización del proceso de postulación (proceso aparte)
├── search_worker.py            # Búsqueda de vacantes (proceso aparte)
├── semantic_filter.py          # Filtrado por matching semántico
├── evaluate_semantic_filter.py # Evaluación del filtro semántico
├── calibrate_threshold.py      # Calibración de los umbrales de similitud (ALTA/MEDIA/BAJA)
├── decision_maker.py           # Motor de decisión + explicaciones XAI
├── feedback.py                 # Retroalimentación adaptativa y detección de skill gaps
├── config.py                   # Configuración general
├── debug_ct.py                 # Herramientas de depuración
│
├── historial_postulaciones.db  # Base de datos SQLite (se genera automáticamente)
├── requirements.txt
└── README.md
```

---

# Requisitos

- Python 3.11 o superior
- Google Chrome / Chromium (usado por Playwright)

---

# Instalación

## Clonar el repositorio

```bash
git clone https://github.com/DanSotos/TalentScout-IA_v2.git

cd TalentScout-IA_v2
```

## Crear un entorno virtual (opcional)

### Windows

```bash
python -m venv venv

venv\Scripts\activate
```

### Linux/macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

## Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

---

# Configuración

Crear un archivo `.env` en la raíz del proyecto con las credenciales necesarias para los portales de empleo (según los scrapers habilitados en `config.py`).

**No compartas ni subas este archivo al repositorio.**

---

# Ejecución

## Interfaz gráfica (recomendada)

```bash
streamlit run app.py --server.fileWatcherType none
```

Una vez iniciado, abre el navegador en:

```
http://localhost:8501
```

## Ejecución desde consola

```bash
python main.py
```

---

# Flujo de trabajo

1. Cargar el CV del candidato.
2. Especificar el cargo/puesto deseado y preferencias de búsqueda.
3. Buscar ofertas laborales en los portales configurados.
4. Calcular la similitud semántica CV–vacante (Sentence-BERT).
5. Clasificar cada vacante en ALTA / MEDIA / BAJA compatibilidad, con explicación XAI.
6. Revisar las recomendaciones.
7. Autorizar la postulación (supervisión del usuario).
8. Registrar el historial y las brechas de habilidades detectadas.

---

# Limitaciones conocidas

- **Precisión del cargo deseado:** además del matching por similitud semántica, el sistema incluye un filtro por cargo/puesto (`utils/career_filter.py`). Aun así, se recomienda que el usuario especifique el cargo deseado de forma precisa para reducir la posibilidad de recibir vacantes de profesiones distintas a la buscada.
- Compatible únicamente con las plataformas implementadas en `scrapers/`.
- Requiere conexión a Internet.
- Los cambios en la estructura HTML de los portales de empleo pueden afectar el funcionamiento de los scrapers.
- Las cartas de presentación se generan mediante una plantilla local, no mediante un modelo de lenguaje externo.

---

# Licencia

MIT License.

---

GitHub: https://github.com/DanSotos