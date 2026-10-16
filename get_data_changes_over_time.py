import requests
import time
import json
import hashlib
import difflib
from xml.etree import ElementTree as ET
import re
from pathlib import Path

REGULATIONS = {
    "1002": "Regulation B - Equal Credit Opportunity Act",
    "1003": "Regulation C - Home Mortgage Disclosure",
    "1005": "Regulation E - Electronic Fund Transfers",
    "1006": "Regulation F - Fair Debt Collection Practices Act",
    "1016": "Regulation P - Privacy",
    "1022": "Regulation V - Fair Credit Reporting",
    "1024": "Regulation X - RESPA",
    "1026": "Regulation Z - Truth in Lending",
    "1030": "Regulation DD - Truth in Savings",
    "1041": "Payday Lending Rule",
}

OUTPUT_DIR = Path("cfpb_corpus")
OUTPUT_DIR.mkdir(exist_ok=True)
(OUTPUT_DIR / "snapshots").mkdir(exist_ok=True)
(OUTPUT_DIR / "diffs").mkdir(exist_ok=True)

HEADERS = {"User-Agent": "research-corpus-builder/1.0"}

# def xml_to_text(xml_bytes: bytes) -> str:
#     root = ET.fromstring(xml_bytes)
#     parts = []
#     for node in root.iter():
#         if node.text and node.text.strip():
#             parts.append(node.text.strip())
#         if node.tail and node.tail.strip():
#             parts.append(node.tail.strip())
#     return re.sub(r'\s+', ' ', ' '.join(parts)).strip()

def xml_to_text(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    parts = []
    for node in root.iter():
        if node.text and node.text.strip():
            parts.append(node.text.strip())
        if node.tail and node.tail.strip():
            parts.append(node.tail.strip())

    text = re.sub(r'\s+', ' ', ' '.join(parts)).strip().lower()
    # Strip eCFR navigation artifacts — these repeat across sections
    # and are not part of the regulatory text itself
    text = re.sub(r'link to an amendment published at [\d\w\s,\.]+\.', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_change_dates(part: str) -> list[str]:
    """Get only the dates this specific part was actually amended."""
    resp = requests.get(
        "https://www.ecfr.gov/api/versioner/v1/versions/title-12.json",
        params={"part": part},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    # return sorted(v["date"] for v in resp.json()["content_versions"])

    # AFTER
    return sorted(set(v["date"] for v in resp.json()["content_versions"]))

def fetch_text(date: str, part: str) -> str:
    resp = requests.get(
        f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-12.xml",
        params={"part": part},
        headers=HEADERS,
        timeout=60,
    )
    resp.raise_for_status()
    return xml_to_text(resp.content)

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]

# def make_diff(prev: str, curr: str, prev_date: str, curr_date: str) -> dict:
#     prev_lines = prev.splitlines()
#     curr_lines = curr.splitlines()
#     ops = list(difflib.unified_diff(
#         prev_lines, curr_lines,
#         fromfile=prev_date, tofile=curr_date,
#         lineterm=""
#     ))
#     return {
#         "from_date": prev_date,
#         "to_date": curr_date,
#         "added": sum(1 for l in ops if l.startswith("+")),
#         "removed": sum(1 for l in ops if l.startswith("-")),
#         "patch": "\n".join(ops),
#     }
#
# def make_diff(prev: str, curr: str, prev_date: str, curr_date: str) -> dict:
#     prev_lines = prev.splitlines()
#     curr_lines = curr.splitlines()
#     ops = list(difflib.unified_diff(prev_lines, curr_lines, lineterm=""))
#
#     changes = []
#     for line in ops:
#         if line.startswith("+") and not line.startswith("+++"):
#             changes.append(f"new line: {line[1:].strip()}")
#         # elif line.startswith("-") and not line.startswith("---"):
#         #     changes.append(f"deleted line: {line[1:].strip()}")
#
#         #TODO: later, might want to bring the deletions back in also, but wanted to focus on additions for now
#
#
#     return {
#         "from_date": prev_date,
#         "to_date": curr_date,
#         "added": sum(1 for l in changes if l.startswith("new")),
#         "removed": sum(1 for l in changes if l.startswith("deleted")),
#         "changes": changes,
#     }


# def make_diff(prev: str, curr: str, prev_date: str, curr_date: str) -> dict:
#     prev_words = prev.split()
#     curr_words = curr.split()
#
#     matcher = difflib.SequenceMatcher(None, prev_words, curr_words, autojunk=False)
#     changes = []
#
#     for tag, i1, i2, j1, j2 in matcher.get_opcodes():
#         if tag == "replace":
#             changes.append({
#                 "type": "replace",
#                 "from": " ".join(prev_words[i1:i2]),
#                 "to": " ".join(curr_words[j1:j2]),
#             })
#         elif tag == "insert":
#             changes.append({
#                 "type": "insert",
#                 "to": " ".join(curr_words[j1:j2]),
#             })
#         elif tag == "delete":
#             changes.append({
#                 "type": "delete",
#                 "from": " ".join(prev_words[i1:i2]),
#             })
#
#     return {
#         "from_date": prev_date,
#         "to_date": curr_date,
#         "added": sum(1 for c in changes if c["type"] in ("insert", "replace")),
#         "removed": sum(1 for c in changes if c["type"] in ("delete", "replace")),
#         "changes": changes,
#     }

import re

def is_trivial_change(from_text: str, to_text: str) -> bool:
    # Normalize dashes and surrounding spaces, then compare
    normalize = lambda s: re.sub(r'\s*[-–—]\s*', '-', s).strip()
    if normalize(from_text) == normalize(to_text):
        return True
    # Also skip pure whitespace differences
    if from_text.replace(" ", "") == to_text.replace(" ", ""):
        return True
    return False

# def deduplicate_changes(changes: list) -> list:
#     seen = set()
#     result = []
#     for c in changes:
#         # Build a normalized key to detect duplicates
#         key = (c["type"], c.get("from", ""), c.get("to", ""))
#         if key not in seen:
#             seen.add(key)
#             result.append(c)
#     return result





def make_diff(prev: str, curr: str, prev_date: str, curr_date: str) -> dict:
    prev_words = prev.split()
    curr_words = curr.split()

    matcher = difflib.SequenceMatcher(None, prev_words, curr_words, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            from_text = " ".join(prev_words[i1:i2])
            to_text = " ".join(curr_words[j1:j2])
            if is_trivial_change(from_text, to_text):
                continue
            changes.append({"type": "replace", "from": from_text, "to": to_text})
        elif tag == "insert":
            changes.append({"type": "insert", "to": " ".join(curr_words[j1:j2])})
        elif tag == "delete":
            changes.append({"type": "delete", "from": " ".join(prev_words[i1:i2])})
        seen = set()
        unique_changes = []
        for c in changes:
            key = (c["type"], c.get("from", ""), c.get("to", ""))
            if key not in seen:
                seen.add(key)
                unique_changes.append(c)

    return {
        "from_date": prev_date,
        "to_date": curr_date,
        "added": sum(1 for c in changes if c["type"] in ("insert", "replace")),
        "removed": sum(1 for c in changes if c["type"] in ("delete", "replace")),
        "changes": changes,
    }
# Master index: part -> {dates, snapshots, diffs}
index_path = OUTPUT_DIR / "index.json"
index = json.loads(index_path.read_text()) if index_path.exists() else {}

for part, name in REGULATIONS.items():
    print(f"\nPart {part}: {name}")

    if part not in index:
        index[part] = {"name": name, "versions": []}

    already_done = {v["date"] for v in index[part]["versions"]}
    change_dates = get_change_dates(part)
    new_dates = [d for d in change_dates if d not in already_done]

    if not new_dates:
        print(f"  Up to date ({len(change_dates)} versions)")
        continue

    print(f"  {len(change_dates)} total change dates, {len(new_dates)} new to fetch")

    # Load the last known text to diff against
    prev_text = None
    prev_date = None
    if index[part]["versions"]:
        last = index[part]["versions"][-1]
        snap_path = OUTPUT_DIR / "snapshots" / f"{part}_{last['snapshot']}.txt"
        prev_text = snap_path.read_text(encoding="utf-8")
        prev_date = last["date"]

    for date in new_dates:
        try:
            curr_text = fetch_text(date, part)
            curr_hash = text_hash(curr_text)

            version_entry = {"date": date, "hash": curr_hash}

            if prev_text is None:
                # First version — store full snapshot, no diff
                snap_file = OUTPUT_DIR / "snapshots" / f"{part}_{curr_hash}.txt"
                snap_file.write_text(curr_text, encoding="utf-8")
                version_entry["snapshot"] = curr_hash
                version_entry["change_type"] = "initial"
                print(f"  ✓ {date} — initial snapshot ({len(curr_text):,} chars)")

            elif curr_text == prev_text:
                # API returned same content despite listing as changed — skip
                version_entry["snapshot"] = index[part]["versions"][-1]["snapshot"]
                version_entry["change_type"] = "no_change"
                print(f"  — {date} — listed as changed but text identical, skipping")

            else:
                # Store diff only; point snapshot back to last full text
                diff = make_diff(prev_text, curr_text, prev_date, date)
                # diff_path = OUTPUT_DIR / "diffs" / f"{part}_{prev_date}_to_{date}.json"
                # diff_path.write_text(json.dumps(diff, indent=2), encoding="utf-8")
                # diff_path = OUTPUT_DIR / "diffs" / f"{part}_{prev_date}_to_{date}.txt"
                # diff_path.write_text("\n".join(diff["changes"]), encoding="utf-8")
                diff_path = OUTPUT_DIR / "diffs" / f"{part}_{prev_date}_to_{date}.txt"
                lines = []
                for c in diff["changes"]:
                    if c["type"] == "replace":
                        lines.append(f'~ "{c["from"]}" → "{c["to"]}"')
                    elif c["type"] == "insert":
                        lines.append(f'+ "{c["to"]}"')
                    elif c["type"] == "delete":
                        lines.append(f'- "{c["from"]}"')
                diff_path.write_text("\n".join(lines), encoding="utf-8")

                # Store new full snapshot (lets you reconstruct any version cheaply)
                snap_file = OUTPUT_DIR / "snapshots" / f"{part}_{curr_hash}.txt"
                snap_file.write_text(curr_text, encoding="utf-8")

                version_entry["snapshot"] = curr_hash
                version_entry["diff_from"] = prev_date
                version_entry["change_type"] = "amended"
                print(f"  ✓ {date} — +{diff['added']} / -{diff['removed']} lines")

            index[part]["versions"].append(version_entry)
            prev_text = curr_text
            prev_date = date

            # Save index after every successful fetch so you can resume
            index_path.write_text(json.dumps(index, indent=2))
            time.sleep(1.5)

        except Exception as e:
            print(f"  ✗ {date} — {e}")