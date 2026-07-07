from __future__ import annotations

import io
import json

import pypdfium2 as pdfium
from PIL import Image

from parse_anything.cli_support import Runtime
from parse_anything.pipeline.imagewrap import image_to_pdf, is_image


def _stdout(runtime: Runtime) -> str:
    assert isinstance(runtime.stdout, io.StringIO)
    return runtime.stdout.getvalue()


def test_is_image_by_suffix_case_insensitive():
    assert is_image("scan.png") and is_image("photo.JPG") and is_image("fax.tiff")
    assert not is_image("doc.pdf") and not is_image("notes.txt") and not is_image("noext")


def test_image_to_pdf_wraps_rgb_into_one_page(tmp_path):
    png = tmp_path / "src.png"
    Image.new("RGB", (200, 120), "white").save(png)
    out = tmp_path / "wrapped.pdf"
    image_to_pdf(str(png), str(out))
    doc = pdfium.PdfDocument(str(out))
    try:
        assert len(doc) == 1                       # exactly one page
        w, h = doc[0].get_size()
        assert w > 0 and h > 0
    finally:
        doc.close()


def test_image_to_pdf_flattens_alpha_without_crashing(tmp_path):
    # PDF has no alpha channel; an RGBA image must be flattened, not raise on save
    png = tmp_path / "rgba.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(png)
    out = tmp_path / "rgba.pdf"
    image_to_pdf(str(png), str(out))              # must not raise
    doc = pdfium.PdfDocument(str(out))
    try:
        assert len(doc) == 1
    finally:
        doc.close()


def test_image_to_pdf_is_byte_deterministic_for_same_image(tmp_path):
    # the wrapped PDF must hash identically across runs (Pillow otherwise stamps a wall-clock date + the
    # output filename into /Title) -- else the content-hash document_id drifts and reprocessing never skips
    import hashlib

    png = tmp_path / "s.png"
    Image.new("RGB", (100, 60), "white").save(png)
    h = []
    for name in ("a.pdf", "b.pdf"):
        image_to_pdf(str(png), str(tmp_path / name))
        h.append(hashlib.sha256((tmp_path / name).read_bytes()).hexdigest())
    assert h[0] == h[1]

    other = tmp_path / "o.png"
    Image.new("RGB", (100, 60), "black").save(other)   # different pixels -> different hash
    image_to_pdf(str(other), str(tmp_path / "c.pdf"))
    assert hashlib.sha256((tmp_path / "c.pdf").read_bytes()).hexdigest() != h[0]


def test_cli_skips_already_processed_image_on_rerun(tmp_path):
    # FR-1 + reprocessing guard: the SAME image re-run is skipped (deterministic wrap -> stable doc id)
    import parse_anything.cli as cli

    png = tmp_path / "scan.png"
    Image.new("RGB", (200, 140), "white").save(png)
    args = ["--pdf", str(png), "--out", str(tmp_path / "out"), "--no-vlm", "--source-id", "s"]

    r1 = cli.Runtime(environ={}, stdout=io.StringIO())
    assert cli.run_cli(args, r1, env_file=tmp_path / "absent.env") == 0
    assert "mode=deterministic" in _stdout(r1)

    r2 = cli.Runtime(environ={}, stdout=io.StringIO())
    assert cli.run_cli(args, r2, env_file=tmp_path / "absent.env") == 0
    assert "skipped:" in _stdout(r2)   # stable hash -> recognized as already processed


def test_cli_corrupt_image_fails_cleanly_without_leaking_temp(tmp_path):
    # a file named .png that Pillow can't decode must yield a clean error + non-zero exit, not a traceback,
    # and must not leave the mkstemp wrapper behind
    import glob
    import tempfile

    import parse_anything.cli as cli

    bad = tmp_path / "broken.png"
    bad.write_bytes(b"this is not a PNG")
    before = set(glob.glob(f"{tempfile.gettempdir()}/*.pdf"))
    runtime = cli.Runtime(environ={}, stdout=io.StringIO())

    code = cli.run_cli(["--pdf", str(bad), "--out", str(tmp_path / "out"), "--no-vlm"], runtime,
                       env_file=tmp_path / "absent.env")

    out = _stdout(runtime)
    assert code == 2 and "could not read image input" in out
    assert "Traceback" not in out
    leaked = set(glob.glob(f"{tempfile.gettempdir()}/*.pdf")) - before
    assert not leaked   # the temp wrapper created before the decode failure was cleaned up


def test_cli_accepts_image_input_and_records_original_as_provenance(tmp_path):
    # FR-1 end-to-end: a PNG runs through the normal deterministic pipeline (wrapped to PDF), and the
    # document's provenance points at the ORIGINAL image, not the throwaway temp wrapper.
    import parse_anything.cli as cli

    png = tmp_path / "receipt.png"
    Image.new("RGB", (300, 200), "white").save(png)
    out = tmp_path / "out"
    runtime = cli.Runtime(environ={}, stdout=io.StringIO())

    code = cli.run_cli(["--pdf", str(png), "--out", str(out), "--no-vlm"], runtime, env_file=tmp_path / "absent.env")

    assert code == 0
    assert "mode=deterministic" in _stdout(runtime)
    docdirs = list((out / "default").glob("*"))
    assert len(docdirs) == 1
    meta = json.loads((docdirs[0] / "document.json").read_text(encoding="utf-8"))
    assert meta["source"]["ingested_from"] == str(png)   # the image, not a /tmp/*.pdf wrapper
    assert meta["original_filename"] == "receipt.png"    # real image name, not the throwaway temp .pdf


def test_cli_multi_frame_image_warns_about_dropped_pages(tmp_path):
    # a multi-page TIFF wraps only frame 1; the user must be told pages were dropped (not silent data loss)
    import parse_anything.cli as cli

    tif = tmp_path / "fax.tiff"
    frames = [Image.new("RGB", (80, 60), c) for c in ("white", "black", "gray")]
    frames[0].save(tif, save_all=True, append_images=frames[1:])
    runtime = cli.Runtime(environ={}, stdout=io.StringIO())

    code = cli.run_cli(["--pdf", str(tif), "--out", str(tmp_path / "out"), "--no-vlm"], runtime,
                       env_file=tmp_path / "absent.env")

    assert code == 0
    assert "only frame 1 of 3 wrapped" in _stdout(runtime)


def test_textless_image_page_is_described_as_page_level_figure(tmp_path):
    from parse_anything.pipeline.docmeta import build_meta
    from parse_anything.pipeline.odl_extract import OdlDocument, OdlPage
    from parse_anything.pipeline.output import write_outputs
    from parse_anything.pipeline.run import DocumentResult, PageOutcome

    png = tmp_path / "drawing.png"
    Image.new("RGB", (240, 160), "white").save(png)
    pdf = tmp_path / "drawing.pdf"
    image_to_pdf(str(png), str(pdf))

    calls: list[tuple[bytes, str | None]] = []

    def describe_figure(image: bytes, caption: str | None) -> str:
        calls.append((image, caption))
        return "KIND: diagram\nSchneckenwelle 16MnCr5 scale 2:1 dia32-0.1 Ra 1.6"

    result = DocumentResult(
        pages=(PageOutcome(0, "det_vlm", True, "", 0.0),),
        structure=OdlDocument(1, (OdlPage(0, "", (), ()),)),
        meta=build_meta(str(pdf), mode="det_vlm", n_pages=1, original_filename=png.name),
    )

    out = tmp_path / "out"
    write_outputs(result, out, pdf_path=str(pdf), describe_figure=describe_figure)

    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert len(calls) == 1 and calls[0][0].startswith(b"\x89PNG") and calls[0][1] is None
    assert doc["pages"][0]["figures"] == ["p1_page"]
    assert doc["pages"][0]["content"] == ["p1_page"]
    assert doc["figures"][0]["source"] == "page_raster"
    assert doc["figures"][0]["kind"] == "diagram"
    assert doc["figures"][0]["description"] == "Schneckenwelle 16MnCr5 scale 2:1 dia32-0.1 Ra 1.6"
    assert (out / doc["figures"][0]["file"]).exists()
    assert "Schneckenwelle 16MnCr5" in (out / "document.md").read_text(encoding="utf-8")


def test_textless_image_page_without_describer_does_not_fabricate_caption(tmp_path):
    from parse_anything.pipeline.docmeta import build_meta
    from parse_anything.pipeline.odl_extract import OdlDocument, OdlPage
    from parse_anything.pipeline.output import write_outputs
    from parse_anything.pipeline.run import DocumentResult, PageOutcome

    png = tmp_path / "drawing.png"
    Image.new("RGB", (240, 160), "white").save(png)
    pdf = tmp_path / "drawing.pdf"
    image_to_pdf(str(png), str(pdf))

    result = DocumentResult(
        pages=(PageOutcome(0, "deterministic", False, "", 0.0),),
        structure=OdlDocument(1, (OdlPage(0, "", (), ()),)),
        meta=build_meta(str(pdf), mode="deterministic", n_pages=1, original_filename=png.name),
    )

    out = tmp_path / "out"
    write_outputs(result, out, pdf_path=str(pdf))

    doc = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert doc["figures"] == []
    assert doc["pages"][0]["figures"] == []
