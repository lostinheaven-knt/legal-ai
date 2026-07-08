from __future__ import annotations

import re
from pathlib import Path

CJK_FONT_NAME = "LegalAICJK"
_CJK_FONT_ERROR_MESSAGE = (
    "risk-report.pdf contains non-ASCII/CJK text, but no local CJK-capable font was found. "
    "Add a bundled font under src/legal_ai/assets/fonts/ or run on a system with a supported "
    "local CJK font path."
)

_BUNDLED_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
CJK_FONT_CANDIDATES = (
    _BUNDLED_FONT_DIR / "NotoSansCJKsc-Regular.otf",
    _BUNDLED_FONT_DIR / "NotoSansSC-Regular.otf",
    _BUNDLED_FONT_DIR / "SourceHanSansSC-Regular.otf",
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/local/share/fonts/NotoSansCJK-Regular.ttc"),
    Path("/opt/homebrew/share/fonts/NotoSansCJK-Regular.ttc"),
)


class CJKFontUnavailableError(ValueError):
    """Raised when non-ASCII PDF text cannot be rendered without lossy fallback."""


def write_risk_report_pdf(
    markdown_text: str,
    output_path: Path,
    *,
    title: str = "Risk Report",
) -> str:
    """Write a plain-text PDF from the rendered risk-report Markdown."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    needs_unicode_font = _requires_unicode_font(f"{title}\n{markdown_text}")
    try:
        _write_reportlab_pdf(markdown_text, output_path, title=title)
    except ModuleNotFoundError as exc:
        if needs_unicode_font:
            raise CJKFontUnavailableError(_CJK_FONT_ERROR_MESSAGE) from exc
        _write_minimal_pdf(markdown_text, output_path, title=title)
    return output_path.as_posix()


def _write_reportlab_pdf(markdown_text: str, output_path: Path, *, title: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = _pdf_styles_for_text(f"{title}\n{markdown_text}", getSampleStyleSheet())
    story = [Paragraph(_inline_markup(title), styles["Title"]), Spacer(1, 12)]
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 8))
            continue
        if stripped.startswith("# "):
            story.append(Paragraph(_inline_markup(stripped[2:]), styles["Title"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(_inline_markup(stripped[3:]), styles["Heading2"]))
        elif stripped.startswith("- "):
            story.append(Paragraph(_inline_markup(f"- {stripped[2:]}"), styles["BodyText"]))
        elif stripped.startswith("|"):
            table_line = _markdown_table_line(stripped)
            story.append(Paragraph(_inline_markup(table_line), styles["BodyText"]))
        else:
            story.append(Paragraph(_inline_markup(stripped), styles["BodyText"]))
    document = SimpleDocTemplate(output_path.as_posix(), pagesize=letter, title=title)
    document.build(story)


def _contains_cjk(text: str) -> bool:
    return any(
        0x2E80 <= ord(char) <= 0x2EFF
        or 0x3000 <= ord(char) <= 0x303F
        or 0x3040 <= ord(char) <= 0x30FF
        or 0x3400 <= ord(char) <= 0x4DBF
        or 0x4E00 <= ord(char) <= 0x9FFF
        or 0xF900 <= ord(char) <= 0xFAFF
        or 0x20000 <= ord(char) <= 0x2A6DF
        or 0x2A700 <= ord(char) <= 0x2B73F
        or 0x2B740 <= ord(char) <= 0x2B81F
        or 0x2B820 <= ord(char) <= 0x2CEAF
        for char in text
    )


def _requires_unicode_font(text: str) -> bool:
    return any(ord(char) > 127 for char in text)


def _resolve_cjk_font_path() -> Path | None:
    for candidate in CJK_FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _register_cjk_font(font_path: Path) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if CJK_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return CJK_FONT_NAME
    try:
        pdfmetrics.registerFont(TTFont(CJK_FONT_NAME, font_path.as_posix(), subfontIndex=0))
    except TypeError:
        try:
            pdfmetrics.registerFont(TTFont(CJK_FONT_NAME, font_path.as_posix()))
        except Exception as exc:
            raise CJKFontUnavailableError(_CJK_FONT_ERROR_MESSAGE) from exc
    except Exception as exc:
        raise CJKFontUnavailableError(_CJK_FONT_ERROR_MESSAGE) from exc
    return CJK_FONT_NAME


def _pdf_styles_for_text(text: str, styles):
    if not _requires_unicode_font(text):
        return styles

    font_path = _resolve_cjk_font_path()
    if font_path is None:
        raise CJKFontUnavailableError(_CJK_FONT_ERROR_MESSAGE)

    font_name = _register_cjk_font(font_path)
    styles["Title"].fontName = font_name
    styles["Heading2"].fontName = font_name
    styles["BodyText"].fontName = font_name
    return styles


def _write_minimal_pdf(markdown_text: str, output_path: Path, *, title: str) -> None:
    lines = [title, *[_markdown_table_line(line.strip()) for line in markdown_text.splitlines()]]
    pages = _paginate([_plain_text(line) for line in lines if line.strip()])
    objects: list[bytes] = []
    page_object_numbers: list[int] = []

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    font_object_number = 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page in pages:
        content = _page_stream(page)
        content_object_number = len(objects) + 1
        objects.append(
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
        page_object_number = len(objects) + 1
        page_object_numbers.append(page_object_number)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                f"/Contents {content_object_number} 0 R >>"
            ).encode("ascii")
        )

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode(
        "ascii"
    )
    _write_pdf_objects(output_path, objects)


def _write_pdf_objects(output_path: Path, objects: list[bytes]) -> None:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets: list[int] = []
    byte_count = len(chunks[0])
    for index, obj in enumerate(objects, start=1):
        offsets.append(byte_count)
        chunk = f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        chunks.append(chunk)
        byte_count += len(chunk)
    xref_offset = byte_count
    xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")]
    xref.extend(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets)
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    output_path.write_bytes(b"".join([*chunks, *xref, trailer]))


def _paginate(lines: list[str], *, max_lines: int = 48) -> list[list[str]]:
    if not lines:
        return [["Risk Report"]]
    return [lines[index : index + max_lines] for index in range(0, len(lines), max_lines)]


def _page_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line[:110])}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def _markdown_table_line(line: str) -> str:
    if line.startswith("|---"):
        return ""
    if line.startswith("|"):
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        return " | ".join(cell for cell in cells if cell)
    return line


def _inline_markup(text: str) -> str:
    from html import escape

    return escape(_plain_text(text))


def _plain_text(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return text.replace("\u2022", "-")


def _pdf_escape(text: str) -> str:
    ascii_text = text.encode("ascii", "replace").decode("ascii")
    return ascii_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
