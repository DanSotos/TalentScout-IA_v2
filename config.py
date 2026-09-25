"""
config.py - Configuración centralizada del proyecto job-agent
"""
import os
from pathlib import Path

# ============================================================================
# RUTAS BASE
# ============================================================================
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
CV_DIR = DATA_DIR / "cv"
VACANCIES_DIR = DATA_DIR / "vacancies"
LOGS_DIR = DATA_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"

# Crear directorios si no existen
for dir_path in [DATA_DIR, CV_DIR, VACANCIES_DIR, LOGS_DIR, CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ============================================================================
# MODELOS DE IA
# ============================================================================
# Sentence-Transformer para embeddings
SENTENCE_BERT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  
# Alternativa multilingüe: "paraphrase-multilingual-MiniLM-L12-v2"

# ============================================================================
# UMBRALES DE SIMILITUD
# ============================================================================

SIGNAL_TEXT_WEIGHT = 0.65


COSINE_SIMILARITY_THRESHOLD_HIGH   = 0.32
COSINE_SIMILARITY_THRESHOLD_MEDIUM = 0.25


# ============================================================================
# DECISIONES AUTÓNOMAS
# ============================================================================

AUTO_APPLY_HIGH_COMPATIBILITY = True 
AUTO_APPLY_MEDIUM_COMPATIBILITY = False

# ============================================================================
# CONFIGURACIÓN DE SCRAPERS
# ============================================================================
# URLs base de los portales de empleo
SCRAPER_CONFIG = {
    "computrabajo": {
        "base_url": "https://www.computrabajo.com.pe",
        "search_endpoint": "/jobs/",
        "use_selenium": False,  
    },
    "linkedin": {
        "base_url": "https://www.linkedin.com",
        "search_endpoint": "/jobs/search/",
        "use_selenium": True,  
    },
    "indeed": {
        "base_url": "https://www.indeed.com",
        "search_endpoint": "/jobs",
        "use_selenium": False,
    },
}

# ============================================================================
# SETTINGS DE RED
# ============================================================================
REQUEST_TIMEOUT = 30  
MAX_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ============================================================================
# EXPLAINABILITY (XAI)
# ============================================================================
ENABLE_XAI = True  
MAX_KEYWORDS_FOR_EXPLANATION = 5  