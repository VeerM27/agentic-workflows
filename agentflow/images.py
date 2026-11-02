"""Image preparation for agents: inspect, crop, resize, cut out, export web sizes, strip metadata.

Used through `agentflow image ...` (Claude Code backend) and the `prepare_image` tool (API backend).
Every input and output path must stay inside a root folder (the agent's workspace).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

FORMATS = {"webp": "WEBP", "png": "PNG", "jpeg": "JPEG", "jpg": "JPEG"}
_MASK_MAX = 1200  # the background flood-fill runs on a copy at most this many pixels wide/tall


class ImageError(Exception):
    """An image operation that cannot be done (bad path, unsupported file, invalid request)."""


def inside(path: str | Path, root: str | Path) -> Path:
    """Resolve `path` (relative to `root` if not absolute) and refuse anything outside `root`."""
    root = Path(root).resolve()
    candidate = Path(path)
    candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if candidate != root and root not in candidate.parents:
        raise ImageError(f"'{path}' is outside the workspace")
    return candidate


def _open(src: Path) -> Image.Image:
    if not src.is_file():
        raise ImageError(f"file not found: {src.name}")
    try:
        im = Image.open(src)
        im.load()
    except Exception as exc:  # PIL raises several types for unreadable files
        raise ImageError(f"{src.name} is not an image Pillow can read ({exc})") from exc
    return ImageOps.exif_transpose(im)  # respect camera orientation before dropping EXIF


def _clean(im: Image.Image) -> Image.Image:
    """A copy with pixel data only: no EXIF, XMP, ICC or text chunks."""
    mode = "RGBA" if _has_alpha(im) else "RGB"
    out = Image.new(mode, im.size)
    out.paste(im.convert(mode))
    return out


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def _save(im: Image.Image, out: Path, fmt: str | None = None) -> None:
    fmt = (fmt or out.suffix.lstrip(".")).lower()
    if fmt not in FORMATS:
        raise ImageError(f"unsupported output format '{fmt}' (use {', '.join(sorted(set(FORMATS) - {'jpg'}))})")
    out.parent.mkdir(parents=True, exist_ok=True)
    im = _clean(im)
    if FORMATS[fmt] == "JPEG":
        if im.mode == "RGBA":
            raise ImageError("JPEG has no transparency; export as webp or png")
        im.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    elif FORMATS[fmt] == "WEBP":
        im.save(out, "WEBP", quality=86, method=6)
    else:
        im.save(out, "PNG", optimize=True)


# --- operations ------------------------------------------------------------------------


@dataclass
class ImageInfo:
    path: str
    format: str
    width: int
    height: int
    mode: str
    has_alpha: bool
    bytes: int
    metadata: list[str] = field(default_factory=list)

    def describe(self) -> str:
        meta = ", ".join(self.metadata) if self.metadata else "none"
        alpha = "yes" if self.has_alpha else "no (opaque background)"
        return (
            f"{self.path}: {self.width}×{self.height}px, {self.format}, {self.bytes / 1024:.0f} KB\n"
            f"  transparency: {alpha}\n"
            f"  metadata: {meta}\n"
            f"  sharp up to about {self.width // 2}px wide on high-density screens "
            f"({self.width}px on standard screens)"
        )


def info(src: str | Path, root: str | Path) -> ImageInfo:
    path = inside(src, root)
    if not path.is_file():
        raise ImageError(f"file not found: {src}")
    try:
        with Image.open(path) as im:
            meta: list[str] = []
            exif = im.getexif()
            if exif:
                meta.append("EXIF")
                if 0x8825 in exif and exif.get_ifd(0x8825):
                    meta.append("GPS location")
                for tag, name in ((0x010F, "camera make"), (0x0110, "camera model"), (0x013B, "author")):
                    if exif.get(tag):
                        meta.append(name)
            if any(k in im.info for k in ("xmp", "XML:com.adobe.xmp")):
                meta.append("XMP")
            if "icc_profile" in im.info:
                meta.append("ICC colour profile")
            text = [k for k in im.info if k not in ("dpi", "gamma", "transparency", "icc_profile", "xmp",
                                                     "XML:com.adobe.xmp", "exif", "aspect", "jfif",
                                                     "jfif_version", "jfif_density", "jfif_unit",
                                                     "progressive", "progression", "loop", "duration",
                                                     "background", "srgb", "chromaticity", "adobe",
                                                     "adobe_transform")]
            if text:
                meta.append("text: " + ", ".join(text))
            return ImageInfo(
                path=str(src), format=im.format or "?", width=im.width, height=im.height, mode=im.mode,
                has_alpha=_has_alpha(im), bytes=path.stat().st_size, metadata=meta,
            )
    except ImageError:
        raise
    except Exception as exc:
        raise ImageError(f"{src} is not an image Pillow can read ({exc})") from exc


def crop(src: str | Path, out: str | Path, box: tuple[int, int, int, int], root: str | Path) -> str:
    x, y, w, h = (int(v) for v in box)
    im = _open(inside(src, root))
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > im.width or y + h > im.height:
        raise ImageError(f"box {x},{y},{w},{h} is outside the {im.width}×{im.height} image")
    target = inside(out, root)
    _save(im.crop((x, y, x + w, y + h)), target)
    return f"Cropped {w}×{h}px from {src} → {out}"


def resize(src: str | Path, out: str | Path, width: int, root: str | Path, allow_upscale: bool = False) -> str:
    im = _open(inside(src, root))
    width = int(width)
    if width <= 0:
        raise ImageError("width must be positive")
    if width > im.width and not allow_upscale:
        raise ImageError(
            f"{src} is only {im.width}px wide; enlarging it to {width}px adds no detail. "
            "Use the largest size available, or ask for a higher-resolution original."
        )
    height = round(im.height * width / im.width)
    _save(im.resize((width, height), Image.Resampling.LANCZOS), inside(out, root))
    return f"Resized {src} to {width}×{height}px → {out}"


def cutout(src: str | Path, out: str | Path, root: str | Path, tolerance: int = 12) -> str:
    """Make a plain background transparent: flood-fill from the edges over near-background pixels.

    Works for studio shots and illustrations on plain or light backgrounds. Interior areas of the
    same colour that don't touch the background (e.g. a white sole) stay opaque.
    """
    if not 0 <= int(tolerance) <= 100:
        raise ImageError("tolerance must be between 0 and 100")
    im = _open(inside(src, root)).convert("RGBA")
    scale = min(1.0, _MASK_MAX / max(im.size))
    small = im.convert("RGB").resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                                     Image.Resampling.BILINEAR) if scale < 1 else im.convert("RGB")
    sentinel = (1, 254, 3)
    marked = small.copy()
    w, h = marked.size
    px = marked.load()
    border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
             [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    corners = [small.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    bg = tuple(sorted(c[i] for c in corners)[1] for i in range(3))  # robust "typical corner" colour
    limit = int(tolerance) * 3
    for seed in border[:: max(1, len(border) // 400)] + border[-1:]:
        p = px[seed]
        if p == sentinel or sum(abs(p[i] - bg[i]) for i in range(3)) > limit:
            continue
        ImageDraw.floodfill(marked, seed, sentinel, thresh=limit)
    mask = Image.new("L", marked.size, 255)
    mpx, kpx = mask.load(), marked.load()
    for yy in range(h):
        for xx in range(w):
            if kpx[xx, yy] == sentinel:
                mpx[xx, yy] = 0
    if mask.getextrema() == (255, 255):
        raise ImageError("no plain background found at the edges; cutout needs a plain or light background")
    mask = mask.resize(im.size, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(0.6))
    im.putalpha(Image.composite(im.getchannel("A"), Image.new("L", im.size, 0), mask))
    target = inside(out, root)
    if target.suffix.lower() in (".jpg", ".jpeg"):
        raise ImageError("save cut-outs as .png or .webp (JPEG has no transparency)")
    _save(im, target)
    kept = sum(mask.histogram()[128:]) / (im.width * im.height)
    return f"Cut out the background of {src} → {out} ({kept:.0%} of the image kept, transparent elsewhere)"


def export(
    src: str | Path,
    out_dir: str | Path,
    name: str,
    widths: list[int],
    root: str | Path,
    fmt: str = "webp",
) -> str:
    """Write web sizes (never larger than the source), metadata stripped, plus a srcset snippet."""
    im = _open(inside(src, root))
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ImageError(f"unsupported format '{fmt}'")
    ext = "jpg" if FORMATS[fmt] == "JPEG" else fmt
    directory = inside(out_dir, root)
    root_path = Path(root).resolve()
    written, skipped = [], []
    for width in sorted({int(w) for w in widths}):
        if width <= 0:
            raise ImageError("widths must be positive")
        if width > im.width:
            skipped.append(width)
            continue
        height = round(im.height * width / im.width)
        resized = im if width == im.width else im.resize((width, height), Image.Resampling.LANCZOS)
        target = directory / f"{name}-{width}.{ext}"
        _save(resized, target, ext)
        written.append((width, height, target.relative_to(root_path).as_posix()))
    if not written:
        raise ImageError(
            f"{src} is {im.width}px wide, smaller than every requested width {sorted(widths)}; "
            f"request widths up to {im.width}, or ask for a higher-resolution original"
        )
    lines = [f"Wrote (metadata stripped):"] + [f"  {p}  {w}×{h}px" for w, h, p in written]
    if skipped:
        lines.append(
            f"Skipped {', '.join(map(str, skipped))}px: the source is only {im.width}px wide "
            "(enlarging adds no detail). A higher-resolution original would allow these."
        )
    srcset = ", ".join(f"{p} {w}w" for w, _, p in written)
    largest = written[-1]
    lines.append(f'srcset="{srcset}"')
    lines.append(f"Largest version: {largest[0]}px; show it at most {largest[0] // 2}px wide for sharpness on 2× screens.")
    return "\n".join(lines)


def strip(src: str | Path, out: str | Path, root: str | Path) -> str:
    target = inside(out, root)
    _save(_open(inside(src, root)), target)
    return f"Saved {out} without metadata"
