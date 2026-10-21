"""The usual approach, for comparison: turn each record into a line of text, retrieve the top k lines for the
question with BM25, and answer from those lines only.

To isolate retrieval, the reader is Rounds' own engine and the query is expanded with the same vocabulary,
so the only difference is that the answer sees k retrieved records instead of the whole chart.
"""

from __future__ import annotations

import math
from collections import Counter

from .engine import Engine, fmt_value
from .lexicon import norm
from .parse import STOP


def render(r: dict) -> str:
    """One record as the text a document retriever would index."""
    t = r["type"]
    if t == "Observation":
        return f"{r['date']} observation {r['name']} {fmt_value(r)}"
    if t == "Condition":
        return f"{r['date']} condition {r['name']} {r['status']}" + (f" resolved {r['end']}" if r.get("end") else "")
    if t == "MedicationRequest":
        return f"{r['date']} medication {r['name']} {r['status']}" + (f" for {r['reason']}" if r.get("reason") else "")
    if t == "AllergyIntolerance":
        return f"{r['date']} allergy {r['name']} {r.get('category', '')} {' '.join(r.get('reactions', []))}"
    if t == "Immunization":
        return f"{r['date']} immunization vaccine {r['name']}"
    if t == "Encounter":
        return f"{r['date']} encounter visit {r['cls']} {'emergency' if r['cls'] == 'EMER' else ''} {r['name']}" + (f" for {r['reason']}" if r.get("reason") else "")
    return f"{r['date']} procedure {r['name']}"


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avg = sum(len(d) for d in docs) / max(1, len(docs))
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def top(self, query: list[str], k: int) -> list[int]:
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            dl = len(self.docs[i])
            for t in query:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            if s > 0:
                scores.append((-s, i))
        scores.sort()
        return [i for _, i in scores[:k]]


class RagAnswerer:
    def __init__(self, lexicon: dict, k: int = 5):
        self.engine = Engine(lexicon)
        self.k = k
        self._index: dict[str, tuple[BM25, list[dict]]] = {}

    def index(self, chart: dict) -> tuple[BM25, list[dict]]:
        if chart["id"] not in self._index:
            recs = chart["records"]
            self._index = {chart["id"]: (BM25([norm(render(r)).split() for r in recs]), recs)}
        return self._index[chart["id"]]

    def ask(self, chart: dict, question: str) -> dict:
        query = self.engine.parser.parse(question, chart["asOf"])
        words = [t for t in norm(question).split() if t not in STOP]
        if query["concept"]:
            c = self.engine.concepts[query["concept"]]
            words += norm(c["label"]).split()
        bm25, recs = self.index(chart)
        hits = [recs[i] for i in bm25.top(words, self.k)]
        view = dict(chart, records=sorted(hits, key=lambda r: (r["at"], r["type"], r["code"], r["id"])))
        ans = self.engine.run(view, query)
        ans["retrieved"] = [r["id"] for r in hits]
        return ans
