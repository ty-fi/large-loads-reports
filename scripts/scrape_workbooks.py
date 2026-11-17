"""
Download Large Load Economic Development Report Excel workbooks from GA PSC Docket 55378.
Outputs Excel files organized by quarter into inputs/workbooks/{quarter}/.
"""
import re
import time
import zipfile
import io
from pathlib import Path
import requests

# Hardcoded filing manifest (verified 2026-11-17)
# docId 225690 (Q3+Q4 2025 Revised) supersedes 224615 and 225384
FILINGS = [
    ("2024Q1", 218694),
    ("2024Q2", 219697),
    ("2024Q3", 220461),
    ("2024Q4", 221545),
    ("2025Q1", 222764),
    ("2025Q2", 223705),
    # Q3 and Q4 2025 both come from the revised filing (one ZIP, two Excels)
    ("2025Q3+Q4", 225690),
    # 2026Q1 attaches the workbook directly rather than inside a ZIP
    ("2026Q1", 226607),
    ("2026Q2", 227753),
    ("2026Q3", 229481),
]

BASE_URL = "https://psc.ga.gov/search/facts-document/?documentId={}"
SCRIPT_DIR = Path(__file__).parent
OUTPUTS_DIR = SCRIPT_DIR.parent / "inputs"  # workbooks are inputs since the repo reorg
RAW_DIR = OUTPUTS_DIR / "workbooks" / "raw"
WORKBOOKS_DIR = OUTPUTS_DIR / "workbooks"


def get_download_urls(doc_id: int) -> list[str]:
    resp = requests.get(BASE_URL.format(doc_id), timeout=15)
    resp.raise_for_status()
    return re.findall(r'href="(https://services\.psc\.ga\.gov[^"]+)"', resp.text)


def quarter_from_filename(filename: str) -> str | None:
    """Extract quarter label from Excel filename, e.g. 'Q3 2025' → '2025Q3'."""
    m = re.search(r'[Qq](\d)\s*(\d{4})', filename)
    if m:
        return f"{m.group(2)}Q{m.group(1)}"
    return None


def attachment_filename(resp: requests.Response) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename="?([^";]+)"?', cd)
    return m.group(1).strip() if m else resp.url.rsplit("/", 1)[-1]


def fetch_attachments(doc_id: int) -> list[tuple[str, bytes]]:
    """Download every attachment on a filing as (filename, bytes), cached in RAW_DIR.

    Filings come in two shapes: one ZIP holding the workbook and documents
    (most quarters), or the workbook attached directly alongside the PDF and
    Word files (Q1 2026, docId 226607). Both are handled.
    """
    cache_dir = RAW_DIR / str(doc_id)
    if cache_dir.exists() and any(cache_dir.iterdir()):
        print(f"  Cached attachments found: {cache_dir.name}/")
        return [(p.name, p.read_bytes()) for p in sorted(cache_dir.iterdir())]

    urls = get_download_urls(doc_id)
    if not urls:
        print(f"  WARNING: no download URLs found for docId={doc_id}")
        return []
    cache_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for url in urls:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        name = Path(attachment_filename(resp)).name
        (cache_dir / name).write_bytes(resp.content)
        print(f"  Downloaded {name} ({len(resp.content) / 1024 / 1024:.1f} MB)")
        files.append((name, resp.content))
        time.sleep(3)
    return files


def workbooks_in(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Excel workbooks among the attachments, looking inside any ZIPs."""
    found = []
    for name, data in files:
        if name.lower().endswith(".xlsx"):
            found.append((name, data))
        elif name.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(data))
            found += [(Path(n).name, z.read(n)) for n in z.namelist()
                      if n.lower().endswith(".xlsx")]
    return found


def download_and_extract(quarter_label: str, doc_id: int):
    workbooks = workbooks_in(fetch_attachments(doc_id))
    if not workbooks:
        print(f"  WARNING: no Excel workbook attached to docId={doc_id}")
        return

    for fname, data in workbooks:
        # Determine quarter label from filename for multi-Excel ZIPs
        if quarter_label == "2025Q3+Q4":
            q = quarter_from_filename(fname)
            if q is None:
                print(f"  WARNING: could not determine quarter from filename: {fname}")
                continue
            dest_dir = WORKBOOKS_DIR / q
        else:
            dest_dir = WORKBOOKS_DIR / quarter_label

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / fname

        if dest_path.exists():
            print(f"  Already extracted: {dest_path.relative_to(OUTPUTS_DIR)}")
        else:
            dest_path.write_bytes(data)
            print(f"  Extracted: {dest_path.relative_to(OUTPUTS_DIR)}")


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Scraping {len(FILINGS)} filings from GA PSC Docket 55378\n")

    for quarter_label, doc_id in FILINGS:
        print(f"[{quarter_label}] docId={doc_id}")
        download_and_extract(quarter_label, doc_id)
        print()

    # Summary
    print("Summary of extracted workbooks:")
    for quarter_dir in sorted(WORKBOOKS_DIR.iterdir()):
        if quarter_dir.is_dir() and quarter_dir.name != "raw":
            xlsxs = list(quarter_dir.glob("*.xlsx"))
            print(f"  {quarter_dir.name}: {len(xlsxs)} Excel file(s)")
            for f in xlsxs:
                print(f"    {f.name}")


if __name__ == "__main__":
    main()
