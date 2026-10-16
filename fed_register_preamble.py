import requests
import json
import time
from pathlib import Path

HEADERS = {"User-Agent": "research-corpus-builder/1.0"}
OUTPUT_DIR = Path("cfpb_corpus")
PREAMBLE_DIR = OUTPUT_DIR / "preambles"
PREAMBLE_DIR.mkdir(exist_ok=True)

# same CFR parts you're already tracking
REGULATIONS = {
    "1002": "Regulation B",
    "1003": "Regulation C",
    "1005": "Regulation E",
    "1006": "Regulation F",
    "1016": "Regulation P",
    "1022": "Regulation V",
    "1024": "Regulation X",
    "1026": "Regulation Z",
    "1030": "Regulation DD",
    "1041": "Payday Lending Rule",
}

def search_federal_register(part: str, per_page: int = 20) -> list[dict]:
    """
    Search Federal Register for final rules affecting a CFR part.
    Returns list of document metadata.
    """
    results = []
    page = 1

    while True:
        resp = requests.get(
            "https://www.federalregister.gov/api/v1/documents.json",
            params={
                "conditions[type][]":        "RULE",
                "conditions[cfr][title]":    "12",
                "conditions[cfr][part]":     part,
                "conditions[agencies][]":    "consumer-financial-protection-bureau",
                "fields[]": [
                    "document_number",
                    "title",
                    "publication_date",
                    "full_text_xml_url",
                    "html_url",
                    "abstract",
                    "cfr_references",
                    "agencies",
                ],
                "per_page": per_page,
                "page":     page,
                "order":    "oldest",
            },
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results.extend(data["results"])
        print(f"  page {page}: {len(data['results'])} results "
              f"(total {data['count']})")

        if len(results) >= data["count"]:
            break
        page += 1
        time.sleep(0.5)

    return results


def fetch_preamble_text(xml_url: str) -> str:
    """
    Fetch and extract plain text from a Federal Register XML document.
    Focuses on preamble sections: PREAMBLE, SUPLINF, FURINF, DATES, SUMMARY.
    """
    resp = requests.get(xml_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    from xml.etree import ElementTree as ET
    import re

    root = ET.fromstring(resp.content)

    # target preamble sections — this is where policy language lives
    PREAMBLE_TAGS = {
        "PREAMBLE", "SUPLINF", "FURINF", "DATES",
        "SUMMARY", "LSTSUB", "P", "HD", "SECTION",
    }

    parts = []
    for node in root.iter():
        if node.tag in PREAMBLE_TAGS:
            if node.text and node.text.strip():
                parts.append(node.text.strip())
            if node.tail and node.tail.strip():
                parts.append(node.tail.strip())

    text = re.sub(r'\s+', ' ', ' '.join(parts)).strip().lower()
    # strip navigation artifacts (same as snapshot cleaning)
    text = re.sub(
        r'link to an amendment published at [\d\w\s,\.]+\.', '', text,
        flags=re.IGNORECASE
    )
    return re.sub(r'\s+', ' ', text).strip()


# ── main fetch loop ────────────────────────────────────────────────────────────

preamble_index_path = OUTPUT_DIR / "preamble_index.json"
preamble_index = (
    json.loads(preamble_index_path.read_text())
    if preamble_index_path.exists()
    else {}
)

for part, name in REGULATIONS.items():
    print(f"\nPart {part}: {name}")

    if part not in preamble_index:
        preamble_index[part] = {"name": name, "documents": []}

    already_fetched = {
        d["document_number"]
        for d in preamble_index[part]["documents"]
    }

    documents = search_federal_register(part)
    new_docs   = [d for d in documents
                  if d["document_number"] not in already_fetched]

    print(f"  {len(documents)} total documents, "
          f"{len(new_docs)} new to fetch")

    for doc in new_docs:
        doc_num  = doc["document_number"]
        xml_url  = doc.get("full_text_xml_url")

        if not xml_url:
            print(f"  — {doc_num}: no XML URL, skipping")
            continue

        try:
            text = fetch_preamble_text(xml_url)
            if not text:
                print(f"  — {doc_num}: empty text, skipping")
                continue

            # save preamble text
            out_path = PREAMBLE_DIR / f"{part}_{doc_num}.txt"
            out_path.write_text(text, encoding="utf-8")

            preamble_index[part]["documents"].append({
                "document_number": doc_num,
                "title":           doc.get("title", ""),
                "date":            doc.get("publication_date", ""),
                "html_url":        doc.get("html_url", ""),
                "file":            out_path.name,
                "char_count":      len(text),
            })

            print(f"  ✓ {doc_num} ({doc.get('publication_date', '?')}) "
                  f"— {len(text):,} chars")

            preamble_index_path.write_text(
                json.dumps(preamble_index, indent=2)
            )
            time.sleep(1.0)

        except Exception as e:
            print(f"  ✗ {doc_num}: {e}")