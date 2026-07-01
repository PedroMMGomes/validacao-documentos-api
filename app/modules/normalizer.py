import asyncio
import io
import shutil

import fitz
from PIL import Image

from app.config import settings
from app.core.logging import get_logger
from app.modules.vision_jpeg import page_to_jpeg_bytes

logger = get_logger(__name__)

_TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


class NormalizedContent:
    __slots__ = ("pages", "ocr_text", "page_dimensions", "approx_rgb_bytes", "jpeg_payload_bytes")

    def __init__(
        self,
        pages: list[Image.Image],
        ocr_text: str,
        *,
        page_dimensions: list[tuple[int, int]],
        approx_rgb_bytes: int,
        jpeg_payload_bytes: int,
    ):
        self.pages = pages
        self.ocr_text = ocr_text
        self.page_dimensions = page_dimensions
        self.approx_rgb_bytes = approx_rgb_bytes
        self.jpeg_payload_bytes = jpeg_payload_bytes


async def normalize(content: bytes, filename: str) -> NormalizedContent:
    logger.info("normalize | inicio", extra={"filename": filename, "size": len(content)})

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        pages = await asyncio.to_thread(_pdf_to_images, content, settings.PDF_RENDER_DPI)
    else:
        pages = await asyncio.to_thread(_image_to_pages, content)

    pages = await asyncio.to_thread(_apply_max_long_edge_all, pages, settings.NORMALIZE_MAX_LONG_EDGE)

    page_dimensions = [p.size for p in pages]
    approx_rgb_bytes = sum(w * h * 3 for w, h in page_dimensions)
    jpeg_payload_bytes = sum(
        len(page_to_jpeg_bytes(p, settings.LLM_JPEG_QUALITY)) for p in pages
    )

    ocr_text = await asyncio.to_thread(_run_ocr, pages) if _TESSERACT_AVAILABLE else ""

    logger.info(
        "normalize | ok",
        extra={
            "filename": filename,
            "pages": len(pages),
            "ocr_len": len(ocr_text),
            "pdf_render_dpi": settings.PDF_RENDER_DPI if ext == "pdf" else None,
            "normalize_max_long_edge": settings.NORMALIZE_MAX_LONG_EDGE,
            "page_dimensions": page_dimensions,
            "approx_rgb_bytes": approx_rgb_bytes,
            "jpeg_payload_bytes": jpeg_payload_bytes,
        },
    )
    return NormalizedContent(
        pages=pages,
        ocr_text=ocr_text,
        page_dimensions=page_dimensions,
        approx_rgb_bytes=approx_rgb_bytes,
        jpeg_payload_bytes=jpeg_payload_bytes,
    )


def _pdf_to_images(content: bytes, dpi: int) -> list[Image.Image]:
    pages = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(img)
    logger.info("_pdf_to_images | ok", extra={"pages": len(pages), "dpi": dpi})
    return pages


def _image_to_pages(content: bytes) -> list[Image.Image]:
    pages: list[Image.Image] = []
    raw = io.BytesIO(content)
    with Image.open(raw) as img:
        n_frames = getattr(img, "n_frames", 1)
        for i in range(n_frames):
            img.seek(i)
            frame = img.convert("RGB")
            pages.append(frame.copy())
    logger.info("_image_to_pages | ok", extra={"pages": len(pages)})
    return pages


def _cap_long_edge(img: Image.Image, max_long_edge: int) -> Image.Image:
    w, h = img.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return img
    scale = max_long_edge / float(long_edge)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _apply_max_long_edge_all(pages: list[Image.Image], max_long_edge: int) -> list[Image.Image]:
    return [_cap_long_edge(p, max_long_edge) for p in pages]


def _run_ocr(pages: list[Image.Image]) -> str:
    import pytesseract

    texts = []
    for i, page in enumerate(pages):
        try:
            text = pytesseract.image_to_string(page, lang="por+eng").strip()
            if text:
                texts.append(text)
        except Exception as e:
            logger.warning("_run_ocr | pagina_falhou", extra={"page": i, "error": str(e)})

    combined = "\n\n".join(texts)
    logger.info("_run_ocr | ok", extra={"pages_processed": len(pages), "ocr_len": len(combined)})
    return combined
