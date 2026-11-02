"""The image-preparation helper (agentflow/images.py), its CLI and the prepare_image API tool."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from agentflow import images
from agentflow.tools import ToolExecutor
from agentflow.workspace import Workspace


def make_product(path: Path, size=(600, 300), with_gps=False):
    """A red 'shoe' with a white sole on a white background (like a studio shot)."""
    im = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    w, h = size
    d.rectangle((w * 0.1, h * 0.3, w * 0.9, h * 0.7), fill=(165, 32, 45))      # upper
    d.rectangle((w * 0.08, h * 0.7, w * 0.92, h * 0.82), fill=(250, 250, 250), outline=(30, 30, 30))  # white sole
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    if with_gps:
        exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}
    im.save(path, "JPEG", exif=exif.tobytes())
    return path


def test_info_reports_size_alpha_and_metadata(tmp_path):
    make_product(tmp_path / "shoe.jpg", with_gps=True)
    info = images.info("shoe.jpg", tmp_path)
    assert (info.width, info.height, info.has_alpha) == (600, 300, False)
    assert "EXIF" in info.metadata and "GPS location" in info.metadata and "camera make" in info.metadata
    assert "600×300px" in info.describe()


def test_export_never_enlarges_strips_metadata_and_prints_srcset(tmp_path):
    make_product(tmp_path / "shoe.jpg", with_gps=True)
    out = images.export("shoe.jpg", "site/assets", "shoe", [300, 600, 1200], tmp_path)
    assert (tmp_path / "site/assets/shoe-300.webp").is_file() and (tmp_path / "site/assets/shoe-600.webp").is_file()
    assert not (tmp_path / "site/assets/shoe-1200.webp").exists()
    assert "Skipped 1200px" in out
    assert 'srcset="site/assets/shoe-300.webp 300w, site/assets/shoe-600.webp 600w"' in out
    exported = images.info("site/assets/shoe-600.webp", tmp_path)
    assert exported.metadata == []


def test_export_with_only_too_large_widths_explains(tmp_path):
    make_product(tmp_path / "shoe.jpg")
    with pytest.raises(images.ImageError, match="higher-resolution original"):
        images.export("shoe.jpg", "out", "shoe", [1200, 2400], tmp_path)


def test_cutout_removes_plain_background_but_keeps_white_parts_inside(tmp_path):
    make_product(tmp_path / "shoe.png")
    images.cutout("shoe.png", "cut.png", tmp_path)
    cut = Image.open(tmp_path / "cut.png")
    assert cut.mode == "RGBA"
    assert cut.getpixel((5, 5))[3] == 0                      # background corner: transparent
    assert cut.getpixel((300, 150))[3] == 255                # red upper: opaque
    assert cut.getpixel((300, int(300 * 0.76)))[3] == 255    # white sole touching nothing outside: opaque


def test_cutout_refuses_busy_edges(tmp_path):
    im = Image.new("RGB", (50, 50))
    for x in range(50):
        for y in range(50):
            im.putpixel((x, y), ((x * 37) % 256, (y * 53) % 256, ((x + y) * 29) % 256))
    im.save(tmp_path / "noise.png")
    with pytest.raises(images.ImageError, match="plain"):
        images.cutout("noise.png", "out.png", tmp_path, tolerance=0)


def test_resize_refuses_upscaling_and_crop_checks_bounds(tmp_path):
    make_product(tmp_path / "shoe.jpg")
    with pytest.raises(images.ImageError, match="adds no detail"):
        images.resize("shoe.jpg", "big.jpg", 1200, tmp_path)
    images.resize("shoe.jpg", "small.webp", 300, tmp_path)
    assert Image.open(tmp_path / "small.webp").size == (300, 150)
    with pytest.raises(images.ImageError, match="outside the 600×300"):
        images.crop("shoe.jpg", "c.png", (500, 0, 200, 100), tmp_path)
    images.crop("shoe.jpg", "c.png", (0, 0, 100, 50), tmp_path)
    assert Image.open(tmp_path / "c.png").size == (100, 50)


def test_paths_outside_the_workspace_are_refused(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    make_product(ws / "shoe.jpg")
    make_product(tmp_path / "outside.jpg")
    with pytest.raises(images.ImageError, match="outside the workspace"):
        images.strip("shoe.jpg", "../leak.jpg", ws)
    with pytest.raises(images.ImageError, match="outside the workspace"):
        images.info(str(tmp_path / "outside.jpg"), ws)


def test_prepare_image_tool(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path / "inputs").mkdir()
    make_product(tmp_path / "inputs" / "shoe.jpg")
    ex = ToolExecutor(ws)
    assert "600×300px" in ex.run("prepare_image", {"operation": "info", "path": "inputs/shoe.jpg"}).content
    out = ex.run("prepare_image", {"operation": "export", "path": "inputs/shoe.jpg", "out_dir": "site/assets",
                                   "name": "shoe", "widths": [300]})
    assert not out.is_error and "site/assets/shoe-300.webp" in ex.files_written
    bad = ex.run("prepare_image", {"operation": "crop", "path": "inputs/shoe.jpg", "out": "c.png"})
    assert bad.is_error and "needs 'box'" in bad.content


def test_cli_image_commands(tmp_path, monkeypatch, capsys):
    from agentflow.cli import main

    make_product(tmp_path / "shoe.jpg")
    monkeypatch.chdir(tmp_path)
    assert main(["image", "info", "shoe.jpg"]) == 0
    assert "600×300px" in capsys.readouterr().out
    assert main(["image", "export", "shoe.jpg", "--widths", "300,600", "--out-dir", "assets", "--name", "s"]) == 0
    assert "srcset=" in capsys.readouterr().out
    assert main(["image", "resize", "shoe.jpg", "--width", "900", "--out", "x.jpg"]) == 2
    assert "adds no detail" in capsys.readouterr().err
