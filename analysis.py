import re
import json
from pathlib import Path
from collections import Counter, defaultdict

SNAPSHOT_DIR = Path("cfpb_corpus/snapshots")
INDEX_PATH   = Path("cfpb_corpus/index.json")
TARGET_WORD  = "model"
WINDOW       = 10

COMPOUND_TARGETS = [
    "scoring model",
    "pricing model",
    "valuation model",
    "automated valuation",
    "credit model",
    "algorithmic","automated system", "decision system", "underwriting system"
]

PERIODS = {
    "pre-CFPB": ("2000-01-01", "2011-07-20"),
    "Obama":    ("2011-07-21", "2017-01-19"),
    "Trump-1":  ("2017-01-20", "2021-01-19"),
    "Biden":    ("2021-01-20", "2025-01-19"),
    "Trump-2":  ("2025-01-20", "2099-12-31"),
}

STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "and", "or", "for",
    "is", "are", "be", "by", "that", "this", "with", "as",
    "at", "on", "it", "its", "from", "such", "any", "which",
    "shall", "may", "must", "not", "no", "all", "each", "been",
    "have", "has", "if", "than", "under", "other", "section",
}

index = json.loads(INDEX_PATH.read_text())

# ── helpers ───────────────────────────────────────────────────────────────────

def get_period(date_str):
    for period, (start, end) in PERIODS.items():
        if start <= date_str <= end:
            return period
    return None

def kwic(text, word, window=WINDOW):
    tokens  = text.split()
    hits    = []
    counter = Counter()
    for i, tok in enumerate(tokens):
        if re.fullmatch(rf'{re.escape(word)}s?', tok.lower()):
            left  = tokens[max(0, i - window):i]
            right = tokens[i + 1:i + window + 1]
            hits.append({
                "left":  " ".join(left),
                "match": tok,
                "right": " ".join(right),
            })
            neighbors = [t.lower() for t in left + right]
            neighbors = [t for t in neighbors if t not in STOPWORDS
                         and re.match(r'^[a-z]{3,}$', t)]
            counter.update(neighbors)
    return hits, counter

def kwic_phrase(text, phrase, window=WINDOW):
    tokens        = text.split()
    phrase_tokens = phrase.split()
    n             = len(phrase_tokens)
    hits          = []
    counter       = Counter()
    for i in range(len(tokens) - n + 1):
        if [t.lower() for t in tokens[i:i+n]] == phrase_tokens:
            left  = tokens[max(0, i - window):i]
            right = tokens[i + n:i + n + window]
            hits.append({
                "left":  " ".join(left),
                "match": " ".join(tokens[i:i+n]),
                "right": " ".join(right),
            })
            neighbors = [t.lower() for t in left + right]
            neighbors = [t for t in neighbors if t not in STOPWORDS
                         and re.match(r'^[a-z]{3,}$', t)]
            counter.update(neighbors)
    return hits, counter

# ── run across corpus ─────────────────────────────────────────────────────────
# at the bottom of analysis.py, wrap the execution block:
if __name__ == "__main__":
        # all your main loop, print, chart, save code here
    plt.close()  # instead of plt.show()
    all_targets     = [TARGET_WORD] + COMPOUND_TARGETS
    period_counters = defaultdict(lambda: defaultdict(Counter))
    period_hits     = defaultdict(lambda: defaultdict(list))
    seen_snapshots  = set()

    for part, meta in index.items():
        for v in meta["versions"]:
            period = get_period(v.get("date", ""))
            if not period or "snapshot" not in v:
                continue
            snap_key = v["snapshot"]
            if snap_key in seen_snapshots:
                continue
            seen_snapshots.add(snap_key)

            snap_path = SNAPSHOT_DIR / f"{part}_{snap_key}.txt"
            if not snap_path.exists():
                continue

            text = snap_path.read_text(encoding="utf-8")

            hits, counter = kwic(text, TARGET_WORD)
            for h in hits:
                h["date"] = v["date"]
                h["part"] = part
                period_hits[period][TARGET_WORD].append(h)
            period_counters[period][TARGET_WORD].update(counter)

            for phrase in COMPOUND_TARGETS:
                hits, counter = kwic_phrase(text, phrase)
                for h in hits:
                    h["date"] = v["date"]
                    h["part"] = part
                    period_hits[period][phrase].append(h)
                period_counters[period][phrase].update(counter)

    # ── print results ─────────────────────────────────────────────────────────────

    for target in all_targets:
        print(f"\n══ '{target}' ══")
        for period in PERIODS:
            counter = period_counters[period][target]
            total   = sum(counter.values())
            n_hits  = len(period_hits[period][target])
            if total == 0:
                continue
            top = counter.most_common(10)
            print(f"\n  {period} (n={n_hits} hits)")
            for word, count in top:
                bar = "█" * int(count / max(c for _, c in top) * 15)
                print(f"    {word:<20} {count:>4}  {bar}")

    # ── concordance lines ─────────────────────────────────────────────────────────

    print(f"\n── Sample concordance lines ──\n")
    for target in all_targets:
        print(f"\n══ '{target}' ══")
        for period in PERIODS:
            hits = period_hits[period][target]
            if not hits:
                continue
            print(f"  ── {period} ──")
            for h in hits[:3]:
                print(f"    [{h['date']} §{h['part']}]")
                print(f"    ...{h['left']} [{h['match']}] {h['right']}...")
                print()

    # ── neighbor drift ────────────────────────────────────────────────────────────

    print(f"\n── Neighbor drift across periods ──\n")
    for target in all_targets:
        active = [p for p in PERIODS if period_counters[p][target]]
        if len(active) < 2:
            continue
        print(f"\n══ '{target}' ══")
        for i in range(1, len(active)):
            prev = active[i - 1]
            curr = active[i]
            new  = set(period_counters[curr][target]) - set(period_counters[prev][target])
            lost = set(period_counters[prev][target]) - set(period_counters[curr][target])
            print(f"  {prev} → {curr}")
            print(f"    new:  {', '.join(sorted(new)[:15]) or 'none'}")
            print(f"    lost: {', '.join(sorted(lost)[:15]) or 'none'}")

    # ── save ──────────────────────────────────────────────────────────────────────

    out_path = Path("cfpb_corpus/kwic_results.json")
    out_path.write_text(json.dumps({
        "targets": all_targets,
        "window":  WINDOW,
        "periods": {
            period: {
                target: {
                    "hit_count":     len(period_hits[period][target]),
                    "top_neighbors": period_counters[period][target].most_common(50),
                    "hits":          period_hits[period][target][:50],
                }
                for target in all_targets
            }
            for period in PERIODS
        }
    }, indent=2))
    print(f"\nSaved to {out_path}")



    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    # ── collect hit counts per target per period ──────────────────────────────────

    active_periods = [p for p in PERIODS if any(
        period_hits[p][t] for t in all_targets
    )]

    fig, axes = plt.subplots(
        len(all_targets), 1,
        figsize=(10, 3 * len(all_targets)),
        sharex=True
    )

    # handle single-target case
    if len(all_targets) == 1:
        axes = [axes]

    for ax, target in zip(axes, all_targets):
        counts = [len(period_hits[p][target]) for p in active_periods]

        bars = ax.bar(active_periods, counts, color="#4C72B0", alpha=0.85, width=0.5)

        # label each bar with its count
        for bar, count in zip(bars, counts):
            if count > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(counts) * 0.02,
                    str(count),
                    ha="center", va="bottom", fontsize=9
                )

        ax.set_title(f"'{target}'", fontsize=11, fontweight="bold", loc="left")
        ax.set_ylabel("hits")
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.spines[["top", "right"]].set_visible(False)

        if max(counts) == 0:
            ax.set_ylim(0, 1)
            ax.text(0.5, 0.5, "no hits in corpus",
                    transform=ax.transAxes,
                    ha="center", va="center",
                    color="gray", fontsize=9)

    fig.suptitle("CFPB regulatory corpus — 'model' sense frequency by administration",
                 fontsize=13, fontweight="bold", y=1.01)
    fig.tight_layout()

    chart_path = Path("cfpb_corpus/model_timeline.png")
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"Chart saved to {chart_path}")
    plt.show()