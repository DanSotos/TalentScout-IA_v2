"""
utils/cv_parser.py - Utilidad para extraer texto de CVs en diferentes formatos.
Maneja PDF y otros formatos comunes de CV.
"""
from pathlib import Path
from typing import Optional
import io
import re

# Intentar importar pdfplumber (mejor para PDFs)
try:
    import pdfplumber
    PDF_PARSER_AVAILABLE = True
except ImportError:
    PDF_PARSER_AVAILABLE = False

# Fallback: try with PyPDF2
try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False


class CVParser:
    """
    Parser para extraer texto de archivos de CV.
    Soporta PDF, TXT y otros formatos.
    """
    
    @staticmethod
    def extract_text_from_pdf(file_path: Path) -> str:
        """
        Extrae texto de un archivo PDF.
        
        Args:
            file_path: Ruta al archivo PDF.
            
        Returns:
            Texto extraído del PDF.
            
        Raises:
            ValueError: Si no se puede parsear el PDF.
        """
        text = ""
        
        # Intentar con pdfplumber primero (más preciso)
        if PDF_PARSER_AVAILABLE:
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return text.strip()
            except Exception as e:
                print(f"⚠ pdfplumber falló: {e}, intentando con PyPDF2...")
        
        # Fallback a PyPDF2
        if PYPDF2_AVAILABLE:
            try:
                reader = PdfReader(str(file_path))
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
            except Exception as e:
                raise ValueError(f"No se pudo extraer texto del PDF: {e}")
        
        raise ValueError(
            "No se encontró ninguna librería para parsear PDFs. "
            "Instala: pip install pdfplumber"
        )
    
    @staticmethod
    def extract_text_from_file(file_path: Path) -> str:
        """
        Extrae texto de un archivo de CV detectando automáticamente el formato.
        
        Args:
            file_path: Ruta al archivo de CV.
            
        Returns:
            Texto extraído del archivo.
        """
        suffix = file_path.suffix.lower()
        
        if suffix == ".pdf":
            return CVParser.extract_text_from_pdf(file_path)
        elif suffix in [".txt", ".md"]:
            return file_path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"Formato no soportado: {suffix}")
    
    @staticmethod
    def load_cv(cv_path: Path) -> str:
        """
        Carga y parsea un CV desde la ruta especificada.
        
        Args:
            cv_path: Ruta al archivo de CV.
            
        Returns:
            Texto parseado del CV.
        """
        if not cv_path.exists():
            raise FileNotFoundError(f"CV no encontrado: {cv_path}")
        
        return CVParser.extract_text_from_file(cv_path)


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def load_cv_from_directory(cv_dir: Path, filename: str = "cv.pdf") -> str:
    """
    Busca y carga un CV desde un directorio.
    
    Args:
        cv_dir: Directorio donde buscar el CV.
        filename: Nombre del archivo de CV (default: cv.pdf).
        
    Returns:
        Texto del CV.
    """
    cv_path = cv_dir / filename
    
    if not cv_path.exists():
        # Buscar cualquier archivo PDF en el directorio
        pdf_files = list(cv_dir.glob("*.pdf"))
        if pdf_files:
            cv_path = pdf_files[0]
        else:
            raise FileNotFoundError(
                f"No se encontró ningún CV en {cv_dir}. "
                f"Buscando: {filename}"
            )
    
    return CVParser.load_cv(cv_path)


# Encabezados típicos de la sección de educación en CVs en español.
_EDUCATION_HEADERS = [
    "educación", "educacion", "formación académica", "formacion academica",
    "formación", "formacion", "estudios académicos", "estudios",
]

# Patrones típicos para nombrar un título/carrera. Se buscan SOLO dentro
# de la sección de educación (no en "Experiencia"), porque ahí es donde
# aparece la carrera real y no el cargo laboral (evita, por ejemplo,
# capturar "Analista" de un puesto de trabajo genérico).
_DEGREE_PATTERNS = [
    r"(?:bachiller|licenciad[oa]|t[ií]tulo(?:\s+profesional)?|"
    r"ingenier[oa]|egresad[oa])\s+(?:en|de)\s+([A-ZÁÉÍÓÚÑ][^\n,.;]{3,60})",
    r"carrera\s+(?:de|en)\s+([A-ZÁÉÍÓÚÑ][^\n,.;]{3,60})",
]


def extract_career_from_cv(cv_text: str) -> str:
    """
    Intenta extraer la carrera/título profesional desde la sección de
    Educación del CV (NO el último cargo laboral — un cargo como
    "Analista" es genérico y no identifica el rubro real de la
    persona; el título de Educación sí).

    Es un best-effort con regex sobre texto de PDF, que puede venir
    desordenado o sin buenos saltos de línea. Devuelve "" si no
    encuentra nada con suficiente confianza — el resultado está
    pensado para PRELLENAR un campo editable en la UI, nunca para
    usarse a ciegas sin que la persona lo confirme.
    """
    if not cv_text:
        return ""

    lower = cv_text.lower()

    # Ubicar dónde empieza la sección de educación
    start = -1
    for header in _EDUCATION_HEADERS:
        idx = lower.find(header)
        if idx != -1 and (start == -1 or idx < start):
            start = idx
    if start == -1:
        return ""

    # Ventana de texto después del encabezado (suficiente para 1-2 líneas
    # de título, sin llegar a la siguiente sección)
    window = cv_text[start:start + 400]

    for pattern in _DEGREE_PATTERNS:
        match = re.search(pattern, window, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""