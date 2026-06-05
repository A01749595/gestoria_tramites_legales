"""
OCR Service — Tesseract (pytesseract) + PyMuPDF, sin Azure.

Estrategia (replica el pipeline de GestoriaVertiche):
  1) Intentar extracción de texto digital con PyMuPDF (rápido, gratis).
  2) Si la página viene "vacía" o con muy poco texto (PDF escaneado),
     rasterizarla con PyMuPDF y correr Tesseract sobre la imagen.
  3) Tesseract usa `spa+eng` y varios PSM para quedarse con el mejor resultado.
  4) Si todo falla (Tesseract no instalado, PyMuPDF no instalado),
     se reporta el archivo como SIMULATED con el motivo.

Mejoras de extracción (v2):
  - `max_pages` por defecto sube a 10 (antes 4): muchos documentos legales
    tienen fecha de vigencia o folio en página 5+.
  - `zoom` por defecto 3.0 (≈300 DPI): Tesseract recomienda 300 DPI mínimo;
    1.8x daba ~150 DPI y perdía caracteres pequeños.
  - `sparse_text_threshold` sube a 250: dispara OCR en más páginas con
    sólo membretes o encabezados extraídos de PDFs escaneados.
  - Multi-PSM: probamos 4, 6, 3, 11 y elegimos por **score** (longitud +
    palabras válidas), no por longitud cruda — antes ganaba el más ruidoso.
  - Preprocesado adaptativo: además de binarizado por umbral fijo, generamos
    una variante con binarizado de Otsu y otra sin binarizar para escaneos
    limpios; Tesseract se corre sobre todas y gana la mejor.
  - Combinación digital + OCR: si la página digital tiene algo de texto,
    también se hace OCR y se concatena lo no redundante (algunos PDFs
    tienen una capa de texto incompleta sobre la imagen).
  - `preserve_interword_spaces=1`: respeta tabulaciones en tablas/formularios.

Mantiene la misma API pública que el OCRService anterior (extract_text,
runs_log, simulated) para no tener que tocar el resto del backend.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(
        self,
        provider: str = "tesseract",
        supabase_bucket=None,
        tesseract_lang: str = "spa+eng",
        max_pages: int = 10,
        zoom: float = 3.0,
        sparse_text_threshold: int = 250,
        psm_candidates: Tuple[str, ...] = ("6", "4", "3", "11"),
        oem: str = "3",
        # Mantenidos por compatibilidad con código existente:
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        fallback_to_pymupdf: bool = True,
    ):
        """
        Args:
            provider: identificador del proveedor (se reporta en runs_log).
            supabase_bucket: bucket de Supabase para descargar PDFs por path.
            tesseract_lang: idiomas para Tesseract. 'spa+eng' funciona bien
                para documentos legales mexicanos con palabras en inglés.
            max_pages: máximo de páginas a procesar por PDF. Subido a 10
                porque muchos permisos/licencias tienen la fecha de
                vigencia o el folio en la segunda mitad del documento.
            zoom: factor de rasterización para PyMuPDF antes del OCR.
                3.0 ≈ 300 DPI, el mínimo recomendado por Tesseract.
            sparse_text_threshold: si la página digital tiene menos
                caracteres que esto, se considera escaneada y se hace OCR.
            psm_candidates: page segmentation modes a probar. Se elige el
                mejor por score (longitud + ratio de palabras válidas).
                4=columna variable, 6=bloque uniforme, 3=auto, 11=texto disperso.
            oem: OCR engine mode (3 = default, LSTM + legacy).

            api_key, endpoint, fallback_to_pymupdf: ignorados (compat).
        """
        self.provider = provider
        self.supabase_bucket = supabase_bucket
        self.tesseract_lang = tesseract_lang
        self.default_max_pages = max_pages
        self.zoom = zoom
        self.sparse_text_threshold = sparse_text_threshold
        self.psm_candidates = psm_candidates
        self.oem = oem

        # --- Backend PyMuPDF (fitz): obligatorio para todo ---
        try:
            import fitz  # noqa: F401
            self._fitz_available = True
        except ImportError:
            self._fitz_available = False
            logger.warning(
                "OCRService: PyMuPDF (fitz) no está instalado. "
                "Instala con: pip install PyMuPDF"
            )

        # --- Backend Tesseract: opcional pero recomendado ---
        self._tesseract_available = False
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401

            tesseract_bin = shutil.which("tesseract")
            # rutas comunes en macOS si no está en PATH
            if not tesseract_bin and os.path.exists("/opt/homebrew/bin/tesseract"):
                tesseract_bin = "/opt/homebrew/bin/tesseract"
            if not tesseract_bin and os.path.exists("/usr/local/bin/tesseract"):
                tesseract_bin = "/usr/local/bin/tesseract"
            # ruta común en Linux/Streamlit Cloud con packages.txt
            if not tesseract_bin and os.path.exists("/usr/bin/tesseract"):
                tesseract_bin = "/usr/bin/tesseract"

            if tesseract_bin:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = tesseract_bin
                self._tesseract_available = True
                logger.info("OCRService: Tesseract encontrado en %s", tesseract_bin)
            else:
                logger.warning(
                    "OCRService: Tesseract NO está disponible en PATH. "
                    "Solo se podrá extraer texto de PDFs digitales. "
                    "Instala con: apt-get install tesseract-ocr tesseract-ocr-spa"
                )
        except ImportError:
            logger.warning(
                "OCRService: pytesseract o Pillow no instalado. "
                "Instala con: pip install pytesseract pillow"
            )

        self.runs_log: List[Dict[str, Any]] = []

        logger.info(
            "OCRService listo (pymupdf=%s, tesseract=%s, lang=%s, "
            "max_pages=%s, zoom=%.1f, threshold=%s)",
            self._fitz_available, self._tesseract_available, self.tesseract_lang,
            self.default_max_pages, self.zoom, self.sparse_text_threshold,
        )

    # ------------------------------------------------------------------ #
    # Compatibilidad con el código existente                              #
    # ------------------------------------------------------------------ #

    @property
    def simulated(self) -> bool:
        return not self._fitz_available and not self._tesseract_available

    # Atributo legacy que el resto del backend revisaba:
    @property
    def _azure_available(self) -> bool:  # noqa: N802
        return False

    # ------------------------------------------------------------------ #
    # API pública                                                         #
    # ------------------------------------------------------------------ #

    def extract_text(
        self,
        file_path: str,
        document_type: str = "document",
        max_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Devuelve dict con: text, confidence, fields, processing_time, pages,
        source, provider, mode, [error]
        """
        t0 = time.time()
        max_pages = max_pages or self.default_max_pages

        if not self._fitz_available:
            return self._record(
                file_path, t0, mode="SIMULATED",
                error="PyMuPDF no está instalado en este entorno",
            )

        pdf_bytes = self._load_pdf_bytes(file_path)
        if pdf_bytes is None:
            return self._record(
                file_path, t0, mode="SIMULATED",
                error="PDF no encontrado en disco ni en Supabase",
            )

        try:
            result = self._extract_hybrid(pdf_bytes, file_path, t0, max_pages)
            self._log_run(file_path, result)
            return result
        except Exception as e:
            logger.exception("Extracción falló para %s", file_path)
            return self._record(
                file_path, t0, mode="FAILED",
                error=f"{type(e).__name__}: {e}",
            )

    # ------------------------------------------------------------------ #
    # Pipeline híbrido PyMuPDF (digital) + Tesseract (OCR)                #
    # ------------------------------------------------------------------ #

    def _extract_hybrid(
        self,
        pdf_bytes: bytes,
        file_path: str,
        t0: float,
        max_pages: int,
    ) -> Dict[str, Any]:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n = min(len(doc), max_pages)

        # Heurística: documentos con prefijo 'T' o 'avanzado' suelen ser escaneados.
        force_ocr = self._should_force_ocr(file_path)

        pages_text: List[str] = []
        pages_used_ocr = 0
        pages_digital = 0
        pages_hybrid = 0  # páginas donde digital + OCR aportaron información

        for i in range(n):
            page = doc[i]
            text_digital = self._clean_text(page.get_text("text"))

            text_final = text_digital
            page_used_ocr = False
            page_used_digital = bool(text_digital)

            # Disparamos OCR si: forzado, no hay texto, o texto disperso
            should_ocr = (
                self._tesseract_available
                and (force_ocr or self._is_sparse_text(text_digital))
            )

            if should_ocr:
                ocr_text = self._ocr_page(page)
                ocr_text = self._clean_text(ocr_text)

                if ocr_text:
                    # Si el digital también tenía algo, combinamos lo no redundante.
                    # Pasa con PDFs que tienen capa de texto parcial sobre escaneo.
                    if text_digital and len(text_digital) > 40:
                        merged = self._merge_digital_and_ocr(text_digital, ocr_text)
                        # Sólo aceptamos OCR si aportó >15% más texto útil
                        if len(merged) > len(text_digital) * 1.15:
                            text_final = merged
                            page_used_ocr = True
                        else:
                            text_final = text_digital
                    else:
                        # Página sin texto digital útil: nos quedamos con OCR.
                        text_final = ocr_text
                        page_used_ocr = True
                        page_used_digital = False

            if text_final:
                pages_text.append(text_final)
                if page_used_ocr and page_used_digital:
                    pages_hybrid += 1
                elif page_used_ocr:
                    pages_used_ocr += 1
                else:
                    pages_digital += 1

        full_text = "\n\n".join(pages_text)

        # Confianza heurística: 0.95 si fue 100% digital, baja con uso de OCR.
        total_ocr_pages = pages_used_ocr + pages_hybrid
        if total_ocr_pages == 0:
            confidence = 0.95 if full_text else 0.0
        elif pages_hybrid > 0 and pages_digital > 0:
            confidence = 0.85 if full_text else 0.0
        else:
            confidence = 0.78 if full_text else 0.0

        mode = "REAL" if full_text else "FAILED"
        error = None if full_text else "Sin texto extraíble (¿PDF protegido o vacío?)"

        # Etiqueta del proveedor: útil para las stats del dashboard
        if total_ocr_pages > 0 and pages_digital > 0:
            provider_used = "hybrid"
        elif total_ocr_pages > 0:
            provider_used = "tesseract"
        else:
            provider_used = "pymupdf"

        return {
            "text": full_text,
            "confidence": confidence,
            "fields": {},
            "processing_time": round(time.time() - t0, 2),
            "pages": len(pages_text),
            "pages_processed": n,
            "pages_ocr": pages_used_ocr + pages_hybrid,
            "pages_digital": pages_digital,
            "pages_hybrid": pages_hybrid,
            "source": file_path,
            "provider": provider_used,
            "mode": mode,
            "error": error,
        }

    # ------------------------------------------------------------------ #
    # OCR de una página con pytesseract                                   #
    # ------------------------------------------------------------------ #

    def _ocr_page(self, page) -> str:
        """
        Corre Tesseract con varias combinaciones de (preprocesado, PSM) y
        elige la salida con mejor score (longitud + ratio de palabras válidas).
        """
        try:
            import pytesseract

            img_base = self._page_to_pil_image(page, zoom=self.zoom)

            # Generamos varias variantes de preprocesado y dejamos que Tesseract
            # las pruebe todas. La que mejor puntúe gana.
            variants = self._build_preprocess_variants(img_base)

            candidates: List[str] = []
            for variant_name, img in variants:
                for psm in self.psm_candidates:
                    try:
                        cfg = (
                            f"--oem {self.oem} --psm {psm} "
                            "-c preserve_interword_spaces=1"
                        )
                        txt = pytesseract.image_to_string(
                            img,
                            lang=self.tesseract_lang,
                            config=cfg,
                            timeout=45,
                        )
                        txt = self._normalize_ocr_text(txt)
                        if txt:
                            candidates.append(txt)
                    except Exception as e:
                        logger.debug(
                            "Tesseract variant=%s psm=%s falló: %s",
                            variant_name, psm, e,
                        )
                        continue

            if not candidates:
                return ""
            return max(candidates, key=self._score_ocr_text)

        except Exception as e:
            logger.warning("_ocr_page falló: %s", e)
            return ""

    @staticmethod
    def _page_to_pil_image(page, zoom: float):
        import fitz
        from PIL import Image
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return Image.open(io.BytesIO(pix.tobytes("png")))

    @staticmethod
    def _build_preprocess_variants(img):
        """
        Devuelve varias versiones de la imagen para que Tesseract elija la
        que mejor le va. Usar varias variantes recupera escaneos donde una
        sola binarización destruía texto (muy claros, muy oscuros, color de
        fondo). Manteniendo la lista corta para no explotar el tiempo.
        """
        from PIL import ImageFilter, ImageOps

        gray = img.convert("L")
        gray = ImageOps.autocontrast(gray, cutoff=2)

        # Variante 1: escala de grises con sharpening (sin binarizar).
        #   Ideal para escaneos limpios; Tesseract LSTM funciona mejor sin
        #   binarización agresiva.
        v_gray = gray.filter(ImageFilter.SHARPEN)
        v_gray = ImageOps.expand(v_gray, border=12, fill=255)

        # Variante 2: binarizado con umbral medio (170) — bueno para escaneos
        #   con tinta uniforme y fondo blanco limpio.
        v_bin_mid = gray.point(lambda x: 255 if x > 170 else 0).convert("L")
        v_bin_mid = ImageOps.expand(v_bin_mid, border=12, fill=255)

        # Variante 3: binarizado con umbral tipo Otsu calculado sobre el
        #   histograma. Sólo PIL, sin numpy/opencv para no añadir dependencias.
        threshold = _otsu_threshold(gray)
        v_bin_otsu = gray.point(lambda x: 255 if x > threshold else 0).convert("L")
        v_bin_otsu = ImageOps.expand(v_bin_otsu, border=12, fill=255)

        return [
            ("gray_sharpen", v_gray),
            ("bin_170", v_bin_mid),
            (f"bin_otsu_{threshold}", v_bin_otsu),
        ]

    @staticmethod
    def _preprocess_for_ocr(img):
        """Mantengo este método por compatibilidad si alguien lo llama directo."""
        from PIL import ImageFilter, ImageOps
        img = img.convert("L")
        img = ImageOps.autocontrast(img, cutoff=2)
        img = img.filter(ImageFilter.SHARPEN)
        threshold = _otsu_threshold(img)
        img = img.point(lambda x: 255 if x > threshold else 0)
        img = ImageOps.expand(img, border=12, fill=255)
        return img

    # ------------------------------------------------------------------ #
    # Scoring & helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _score_ocr_text(text: str) -> float:
        """
        Score combinado: longitud * (0.4 + 0.6 * ratio de palabras válidas).
        Tokens "buenos" tienen ≥3 caracteres y ≥60% alfabéticos.
        Penaliza salidas largas llenas de basura (lo que pasaba con PSM=4
        en escaneos con borde sucio).
        """
        if not text:
            return 0.0
        tokens = re.findall(r"\S+", text)
        if not tokens:
            return 0.0
        good = 0
        for tok in tokens:
            if len(tok) >= 3:
                letters = sum(1 for c in tok if c.isalpha())
                if letters / len(tok) >= 0.6:
                    good += 1
        ratio = good / len(tokens)
        return len(text) * (0.4 + 0.6 * ratio)

    @staticmethod
    def _merge_digital_and_ocr(digital: str, ocr: str) -> str:
        """
        Concatena el OCR al texto digital sólo si el OCR contiene líneas
        que no aparecen ya en el digital (por substring normalizado).
        Útil para PDFs con capa de texto parcial.
        """
        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", s.lower()).strip()

        digital_norm = _norm(digital)
        extra_lines: List[str] = []
        for line in ocr.splitlines():
            line_norm = _norm(line)
            if len(line_norm) < 6:
                continue
            if line_norm not in digital_norm:
                extra_lines.append(line)
        if not extra_lines:
            return digital
        return digital + "\n\n[OCR-EXTRA]\n" + "\n".join(extra_lines)

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        text = text.replace("\u00a0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()

    @staticmethod
    def _normalize_ocr_text(text: str) -> str:
        """
        Normaliza salidas comunes de Tesseract: ligaduras, comillas raras,
        guiones partidos al final de línea, espacios duplicados, etc.
        """
        if not text:
            return ""
        text = text.replace("\u00a0", " ")
        # Confusiones frecuentes de OCR
        text = text.replace("|", "I")
        text = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff")
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        # Une palabras partidas al final de línea: "transi-\ntorio" -> "transitorio"
        text = re.sub(r"-\n(\w)", r"\1", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()

    def _is_sparse_text(self, text: str) -> bool:
        if not text:
            return True
        text = text.strip()
        if len(text) < self.sparse_text_threshold:
            return True
        tokens = re.findall(r"\w+", text)
        # Sube a 50 tokens (antes 30): páginas con sólo "Página 1 de 4 — folio..."
        # extraído de la capa digital de un escaneo siguen mereciendo OCR.
        return len(tokens) < 50

    @staticmethod
    def _should_force_ocr(path: str) -> bool:
        """Heurística: ciertos archivos sabemos que son escaneados."""
        base = os.path.basename(path).lower()
        return (
            base.startswith("t")
            or "escan" in base
            or "scan" in base
            or "img" in base
            or base.endswith("_ocr.pdf")
        )

    def _load_pdf_bytes(self, file_path: str) -> Optional[bytes]:
        if os.path.isfile(file_path):
            try:
                with open(file_path, "rb") as f:
                    return f.read()
            except Exception as e:
                logger.error("Disco %s: %s", file_path, e)
                return None
        if self.supabase_bucket is not None:
            try:
                return self.supabase_bucket.download(file_path)
            except Exception as e:
                logger.error("Supabase %s: %s", file_path, e)
                return None
        return None

    def _record(
        self, file_path: str, t0: float, mode: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "text": "",
            "confidence": 0.0,
            "fields": {},
            "processing_time": round(time.time() - t0, 2),
            "pages": 0,
            "pages_processed": 0,
            "pages_ocr": 0,
            "pages_digital": 0,
            "pages_hybrid": 0,
            "source": file_path,
            "provider": self.provider,
            "mode": mode,
            "error": error,
        }
        self._log_run(file_path, rec)
        return rec

    def _log_run(self, file_path: str, result: Dict[str, Any]) -> None:
        self.runs_log.append({
            "file": file_path,
            "pages": result.get("pages", 0),
            "pages_processed": result.get("pages_processed", 0),
            "pages_ocr": result.get("pages_ocr", 0),
            "pages_digital": result.get("pages_digital", 0),
            "pages_hybrid": result.get("pages_hybrid", 0),
            "provider": result.get("provider", self.provider),
            "mode": result.get("mode", "?"),
            "error": result.get("error"),
            "confidence": round(result.get("confidence", 0.0), 3),
            "processing_time": round(result.get("processing_time", 0.0), 2),
        })


# ---------------------------------------------------------------------- #
# Otsu threshold helper (sólo PIL, sin numpy)                            #
# ---------------------------------------------------------------------- #

def _otsu_threshold(gray_img) -> int:
    """
    Calcula el umbral óptimo de Otsu sobre una imagen en escala de grises
    de PIL. Devuelve un int 0–255. Mucho mejor que un fijo (170) cuando el
    escaneo está sub/sobreexpuesto.
    """
    histogram = gray_img.histogram()[:256]
    total = sum(histogram)
    if total == 0:
        return 128

    sum_total = sum(i * h for i, h in enumerate(histogram))
    sum_b = 0.0
    w_b = 0.0
    max_var = 0.0
    threshold = 128

    for i in range(256):
        w_b += histogram[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * histogram[i]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = i

    return threshold
