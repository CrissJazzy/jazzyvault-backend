from pathlib import Path

from PIL import Image


class ImageConversionError(Exception):
    pass


def image_to_pdf(input_path: Path, output_path: Path) -> Path:
    """Converts a JPG/PNG image to a single-page PDF."""
    try:
        with Image.open(input_path) as img:
            # PDFs require RGB; PNGs with transparency (RGBA) need
            # flattening onto a white background first, or Pillow raises.
            if img.mode in ("RGBA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                converted = img.convert("RGBA") if img.mode == "P" else img
                rgb_img.paste(converted, mask=converted.split()[-1])
                img_to_save = rgb_img
            else:
                img_to_save = img.convert("RGB")

            img_to_save.save(output_path, "PDF", resolution=150.0)
    except Exception as e:
        raise ImageConversionError(f"Failed to convert image to PDF: {e}")

    return output_path


def pdf_to_images(
    input_path: Path, output_dir: Path, fmt: str = "jpg", dpi: int = 150
) -> list[Path]:
    """
    Converts each page of a PDF to a separate image file.
    Requires poppler-utils (the `pdftoppm`/`pdftocairo` binaries) to be
    installed at the OS level — see Dockerfile.
    """
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError

    pillow_format = "JPEG" if fmt.lower() in ("jpg", "jpeg") else "PNG"

    try:
        pages = convert_from_path(str(input_path), dpi=dpi)
    except PDFInfoNotInstalledError:
        raise ImageConversionError(
            "poppler-utils is not installed on this system. "
            "It must be installed via the Dockerfile for PDF->image conversion to work."
        )
    except Exception as e:
        raise ImageConversionError(f"Failed to convert PDF to images: {e}")

    if not pages:
        raise ImageConversionError("The PDF has no pages to convert.")

    output_paths: list[Path] = []
    stem = input_path.stem
    ext = "jpg" if pillow_format == "JPEG" else "png"

    for i, page in enumerate(pages, start=1):
        # Single-page PDFs get a clean filename; multi-page PDFs get
        # page numbers so nothing overwrites.
        suffix = "" if len(pages) == 1 else f"-page{i}"
        out_path = output_dir / f"{stem}{suffix}.{ext}"
        page.save(out_path, pillow_format)
        output_paths.append(out_path)

    return output_paths
