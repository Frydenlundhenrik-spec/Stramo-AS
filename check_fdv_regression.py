"""FDV uses the same supplier pack in the app and delivery, with scoped metadata."""
import hashlib
import io
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader
from build_standard_fdv import DEFAULT_SOURCES, build_standard_fdv, lag_standard_fdv_pdf, sources
from fdv import lag_fdv_oversikt, lag_fdv_tekst

source_hashes = {
    (folder, name): hashlib.sha256((DEFAULT_SOURCES / folder / name).read_bytes()).hexdigest()
    for folder, name, _, _ in sources
}
expected_pages = 5 + 3 + sum(
    len(PdfReader(DEFAULT_SOURCES / folder / name).pages)
    for folder, name, _, _ in sources
)
with TemporaryDirectory(prefix="stramo-check-fdv-") as temporary:
    output = Path(temporary) / "delivery"
    pdf_path = build_standard_fdv(
        output, project_name="Tasty Fredrikstad", project_number="138",
        room_names=("Kjølerom 1", "Fryserom 1"),
    )
    reader = PdfReader(pdf_path)
    assert len(reader.pages) == expected_pages
    overview = "\n".join(page.extract_text() for page in reader.pages[:5])
    compact_overview = " ".join(overview.split())
    for required in ("Tasty Fredrikstad", "138", "Kjølerom 1", "Fryserom 1", "PE25", "25 µm", "gulvplate"):
        assert required in overview, required
    assert "Revisjon 08" in overview and "26.10.2026" in overview
    assert "oppdragsgiver 22.10.2026" in overview
    assert "10 mm omknekk" in compact_overview and "ombrett" not in overview
    assert "1500 × 3000 mm" in compact_overview
    assert "Revisjon 08 - 26.10.2026" in reader.metadata.subject
    assert len(reader.outline) == 11
    with (output / "Dokumentregister.csv").open(encoding="utf-8-sig", newline="") as stream:
        register = list(csv.DictReader(stream, delimiter=";"))
    assert [reader.get_destination_page_number(item)+1 for item in reader.outline] == [1]+[
        int(entry["PDF_startside"]) for entry in register
    ]
    for number in (1, 2, 3, 4, 5, expected_pages-2, expected_pages-1, expected_pages):
        text = reader.pages[number-1].extract_text()
        assert f"Stramo AS\nSide {number}" in text, number
        assert "Stramo-del" not in text
    for folder, name, _, _ in sources:
        assert hashlib.sha256((output / folder / name).read_bytes()).hexdigest() == source_hashes[(folder, name)]
        assert hashlib.sha256((DEFAULT_SOURCES / folder / name).read_bytes()).hexdigest() == source_hashes[(folder, name)]
    for folder in ("03_Skruer", "04_Fugemasse", "05_Fiberplater"):
        text = PdfReader(output / folder / "00_Dokumentasjon_kommer.pdf").pages[0].extract_text()
        assert "DOKUMENTASJON ETTERSENDES" in text
    app_pdf = lag_standard_fdv_pdf("Tasty Fredrikstad", "138", ("Fryserom 1",))
    app_reader = PdfReader(io.BytesIO(app_pdf))
    assert len(app_reader.pages) == expected_pages
    app_cover = app_reader.pages[0].extract_text()
    assert "Fryserom 1" in app_cover and "Kjølerom 1" not in app_cover
    try:
        build_standard_fdv(Path(temporary) / "missing", Path(temporary) / "no-sources")
    except FileNotFoundError as exc:
        assert "FDV-vedlegg mangler" in str(exc)
    else:
        raise AssertionError("A missing attachment must never produce an incomplete pack")

for room_type, panel in (("Kjølerom", "PIR 80 mm"), ("Fryserom", "PIR 100 mm")):
    frame = lag_fdv_oversikt(panel, room_type, [], [])
    content = frame.to_csv(index=False) + lag_fdv_tekst("Tasty", panel, room_type)
    assert "PE25" in content and "25 µm" in content
    assert "sponplate" not in content and "plastbelegg" not in content and "beskyttelsesfiner" not in content
    if room_type == "Fryserom":
        assert "gulvplate" in frame.to_csv(index=False)
print(f"PASS: FDV scope, {expected_pages} pages, seven unchanged suppliers, three placeholders, PE25 and floor terminology")
