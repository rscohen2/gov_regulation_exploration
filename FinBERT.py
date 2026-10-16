# pip install gensim scipy numpy

import re
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
from gensim.models import Word2Vec
from scipy.linalg import orthogonal_procrustes
from scipy.spatial.distance import cosine

SNAPSHOT_DIR = Path("cfpb_corpus/snapshots")
INDEX_PATH   = Path("cfpb_corpus/index.json")
TARGET_WORD  = "model"
VECTOR_SIZE  = 100
MIN_COUNT    = 2    # low because corpus is small
WINDOW       = 5

PERIODS = {
    "pre-CFPB": ("2000-01-01", "2011-07-20"),
    "Obama":    ("2011-07-21", "2017-01-19"),
    "Trump-1":  ("2017-01-20", "2021-01-19"),
    "Biden":    ("2021-01-20", "2025-01-19"),
    "Trump-2":  ("2025-01-20", "2099-12-31"),
}

# ── build per-period corpora ──────────────────────────────────────────────────
index = json.loads(INDEX_PATH.read_text())

def get_period(date_str):
    for period, (start, end) in PERIODS.items():
        if start <= date_str <= end:
            return period
    return None

def tokenize(text):
    return re.findall(r'\b[a-z]{2,}\b', text.lower())

period_sentences = defaultdict(list)

for part, meta in index.items():
    for v in meta["versions"]:
        period = get_period(v.get("date", ""))
        if not period or "snapshot" not in v:
            continue
        snap_path = SNAPSHOT_DIR / f"{part}_{v['snapshot']}.txt"
        if not snap_path.exists():
            continue
        text = snap_path.read_text(encoding="utf-8")
        sentences = re.split(r'(?<=[.!?])\s+', text)
        period_sentences[period].extend(
            tokenize(s) for s in sentences if len(s) > 10
        )

for period, sents in period_sentences.items():
    print(f"{period}: {len(sents)} sentences")

# ── train one word2vec model per period ───────────────────────────────────────
period_models = {}
for period, sentences in period_sentences.items():
    if len(sentences) < 50:
        print(f"  skipping {period} — too few sentences")
        continue
    m = Word2Vec(
        sentences,
        vector_size=VECTOR_SIZE,
        window=WINDOW,
        min_count=MIN_COUNT,
        workers=4,
        epochs=20,
        seed=42,
    )
    period_models[period] = m
    print(f"  trained {period}: vocab size {len(m.wv)}")

# ── align all models to the first period using Procrustes ─────────────────────
# Find shared vocabulary across all periods
# period_order = [p for p in PERIODS if p in period_models]
# base_period  = period_order[0]
# base_model   = period_models[base_period]

# def align_to_base(base_model, target_model):
#     """Orthogonal Procrustes: find rotation R that maps target → base."""
#     shared_vocab = [
#         w for w in base_model.wv.index_to_key
#         if w in target_model.wv
#     ]
#     print(f"  shared vocab: {len(shared_vocab)} words")
#
#     A = np.array([base_model.wv[w]   for w in shared_vocab])
#     B = np.array([target_model.wv[w] for w in shared_vocab])
#
#     # find orthogonal R minimising ||A - B@R||
#     R, _ = orthogonal_procrustes(B, A)
#     return R, shared_vocab
#
# aligned_vectors = {base_period: base_model.wv}   # base stays as-is
#
# for period in period_order[1:]:
#     model = period_models[period]
#     R, shared = align_to_base(base_model, model)
#
#     # apply rotation to ALL vectors in this period's model
#     class AlignedVectors:
#         pass
#     av = AlignedVectors()
#     av.vocab = {w: model.wv[w] @ R for w in model.wv.index_to_key}
#     av.__getitem__ = lambda self, w: self.vocab[w]
#     aligned_vectors[period] = av
#     print(f"Aligned {period} → {base_period}")
# ── align all models to the first period using Procrustes ─────────────────────
period_order = [p for p in PERIODS if p in period_models]
base_period  = period_order[0]
base_model   = period_models[base_period]

def align_to_base(base_model, target_model):
    shared_vocab = [
        w for w in base_model.wv.index_to_key
        if w in target_model.wv
    ]
    print(f"  shared vocab: {len(shared_vocab)} words")
    A = np.array([base_model.wv[w]   for w in shared_vocab])
    B = np.array([target_model.wv[w] for w in shared_vocab])
    R, _ = orthogonal_procrustes(B, A)
    return R, shared_vocab

# store aligned vectors as plain dicts: word → numpy vector
aligned_vectors = {}

# base period needs no rotation
aligned_vectors[base_period] = {
    w: base_model.wv[w] for w in base_model.wv.index_to_key
}

for period in period_order[1:]:
    model = period_models[period]
    R, shared = align_to_base(base_model, model)
    aligned_vectors[period] = {
        w: model.wv[w] @ R for w in model.wv.index_to_key
    }
    print(f"Aligned {period} → {base_period}")
    # ── measure semantic drift of target word across periods ─────────────────────
    print(f"\n── Cosine distance of '{TARGET_WORD}' between consecutive periods ──")
    for i in range(len(period_order) - 1):
        p1, p2 = period_order[i], period_order[i+1]
        av1, av2 = aligned_vectors[p1], aligned_vectors[p2]
        try:
            v1 = av1[TARGET_WORD] if hasattr(av1, '__getitem__') else av1[TARGET_WORD]
            v2 = av2.vocab[TARGET_WORD] if hasattr(av2, 'vocab') else av2[TARGET_WORD]
            dist = cosine(v1, v2)
            print(f"  {p1} → {p2}: cosine distance = {dist:.4f}")
        except KeyError as e:
            print(f"  {p1} → {p2}: '{TARGET_WORD}' missing in one period — {e}")

    # ── nearest neighbors per period ──────────────────────────────────────────────
    print(f"\n── Nearest neighbors of '{TARGET_WORD}' by period ──")
    for period in period_order:
        av = aligned_vectors[period]  # plain dict: word → vector

        if TARGET_WORD not in av:
            print(f"  {period:12s}: '{TARGET_WORD}' not in vocabulary")
            continue

        target_vec = av[TARGET_WORD]

        sims = [
            (w, 1 - cosine(target_vec, vec))
            for w, vec in av.items()
            if w != TARGET_WORD
        ]
        sims.sort(key=lambda x: -x[1])
        top = [f"{w}({s:.2f})" for w, s in sims[:10]]
        print(f"  {period:12s}: {', '.join(top)}")

    # ── save drift summary ────────────────────────────────────────────────────────
    results = {"target": TARGET_WORD, "periods": {}}
    for period in period_order:
        av = aligned_vectors[period]
        if TARGET_WORD in av:
            results["periods"][period] = av[TARGET_WORD].tolist()

    Path("cfpb_corpus/semantic_drift.json").write_text(json.dumps(results, indent=2))
    print("\nSaved drift vectors to cfpb_corpus/semantic_drift.json")
