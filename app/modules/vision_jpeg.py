import io

from PIL import Image


def page_to_jpeg_bytes(page: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    rgb = page if page.mode == "RGB" else page.convert("RGB")
    rgb.save(buf, format="JPEG", quality=quality, optimize=True, subsampling=0)
    return buf.getvalue()
