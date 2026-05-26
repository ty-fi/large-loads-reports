"""
Download Large Load Economic Development Report Excel workbooks from GA PSC Docket 55378.
Outputs Excel files organized by quarter into outputs/workbooks/{quarter}/.
"""
import re
import time
import zipfile
import io
from pathlib import Path
import requests

# Hardcoded filing manifest (verified 2026-05-16)
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
]

BASE_URL = "https://psc.ga.gov/search/facts-document/?documentId={}"
SCRIPT_DIR = Path(__file__).parent
OUTPUTS_DIR = SCRIPT_DIR.parent / "outputs"
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


def download_and_extract(quarter_label: str, doc_id: int):
    zip_path = RAW_DIR / f"{doc_id}.zip"

    if not zip_path.exists():
        urls = get_download_urls(doc_id)
        if not urls:
            print(f"  WARNING: no download URLs found for docId={doc_id}")
            return
        url = urls[0]
        print(f"  Downloading {url.split('/')[-1]} ...", end=" ", flush=True)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)
        mb = len(resp.content) / 1024 / 1024
        print(f"done ({mb:.1f} MB)")
        time.sleep(3)
    else:
        print(f"  Cached ZIP found: {zip_path.name}")

    z = zipfile.ZipFile(zip_path)
    xlsx_names = [n for n in z.namelist() if n.lower().endswith(".xlsx")]
    if not xlsx_names:
        print(f"  WARNING: no Excel files found in ZIP for docId={doc_id}")
        return

    for xlsx_name in xlsx_names:
        # Determine quarter label from filename for multi-Excel ZIPs
        fname = Path(xlsx_name).name
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
            dest_path.write_bytes(z.read(xlsx_name))
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
