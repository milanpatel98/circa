"""Question -> query. Deterministic, no model: find the medical terms, the time frame and what is being asked.

    "what was her last a1c"            -> latest_value  obs:a1c
    "is he still on a statin?"         -> on_med        medclass:statin
    "any ER visits in the past year"   -> er_visits     window = past 12 months

Anything it cannot place is 'unsupported', and requests for treatment advice are 'advice'.
Both are refused rather than guessed at.
"""

from __future__ import annotations

import re

from .lexicon import norm

STOP = set("""a an the of to in on for and or with is are was were be been being do does did has have had he she they him her them
his their its it this that these those what whats which who whom when where why how any all some me my i you your we our us
please tell show give list get find check pt patient patients s ever still now currently current today recent recently latest last most
there here from by at as about since before after during over past than then up down out into not no yes ok if so can could would will
should may might must also just only much many more less again""".split())

# words the parser looks for, also used to correct small typos ('medicaitons', 'allergys')
CUES = {
    "advice": r"\b(should|recommend\w*|advis\w*|ok to|okay to|safe to|safe for|alright to|can (i|we|you|he|she|they) (give|take|start|stop|use|add|restart|resume)|"
              r"what dose|which dose|what should|how much \w+ should|increase|decrease|titrate|discontinue|switch|prescribe|dosing|uptitrate|wean|taper|worth starting|need to start|needs? (a|an|to)|"
              r"what would you|what do you think|is it time to|would you)\b",
    "age": r"\b(how old|age|years old|date of birth|dob|birthday|born)\b",
    "allergy": r"\b(allerg\w*|reactions?|intoleran\w*|nkda|anaphyla\w*)\b",
    "vaccine": r"\b(vaccin\w*|shots?|jabs?|immuni[sz]\w*|boosters?|inoculat\w*|doses?)\b",
    "er": r"\b(er|ed|emergency|emerg|a e|e r|casualty)\b",
    "outside": r"\b(family|mother|father|mom|dad|siblings?|brothers?|sisters?|parents?|grand\w*|relatives?|mri|x ray|xray|ct|cat scan|ultrasound|"
               r"echo\w*|imaging|scans?|biops\w*|genetic\w*|genes?|dna|insurance|insurer|coverage|copay|doctor|physician|provider|pcp|"
               r"specialist|nurse|diet|eat\w*|exercis\w*|workouts?|sleep\w*|said|say|says|complain\w*|feel\w*|mood|job|occupation|work|"
               r"address|phone|email|married|lives?|pharmacy|cost|price)\b",
    "admit": r"\b(hospitali[sz]\w*|admitted|admissions?|admits?|inpatient|hospital stays?)\b",
    "visit": r"\b(visits?|seen|appointments?|appts?|encounters?|came in|come in|office|check ?ups?|clinic)\b|\blast\b.*\b(see|saw)\b|\b(see|saw)\b.*\blast\b",
    "med": r"\b(meds?|medications?|medicines?|prescri\w*|drugs?|pills?|rx|taking|takes|take|on any|regimen|scripts?)\b",
    "start": r"\b(start\w*|begin|began|begun|first|initiat\w*|put on|commenced|since when|how long)\b",
    "problem": r"\b(problems?|diagnos[ie]s|dx|dxs|conditions?|medical history|pmh|hx|history|issues|comorbidit\w*|illness\w*|diseases?|ailments?|wrong)\b",
    "has": r"\b(have|has|had|diagnos\w*|history of|hx of|hx|dx|dx of|suffer\w*|with|got|gets|known|positive)\b",
    "trend": r"\b(trend\w*|over time|chang\w*|history|series|serial|track\w*|going up|going down|gone up|gone down|go up|go down|went up|went down|increased|decreased|increasing|decreasing|improv\w*|wors\w*|rising|rise|risen|falling|fallen|"
             r"up or down|trajector\w*|progress\w*|graph|plot|how (has|have)|been doing|been like|been trending|over the|past few|last few|"
             r"(last|past|previous|prior) (\d+|few|several|two|three|four|five|six)|over the years|across)\b",
    "trend_weak": r"\b(values|readings|results|levels|numbers|all|every|each)\b",
    "latest": r"\b(latest|last|most recent|recent|current|currently|newest|now|today|lately)\b",
}

NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "a": 1}


def osa_distance(a: str, b: str, limit: int = 2) -> int:
    """Edit distance with adjacent transpositions ('prescirbed' -> 'prescribed' is 1)."""
    if abs(len(a) - len(b)) >= limit:
        return limit
    prev2 = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


# Typo targets for question words (not medical terms, which come from the vocabulary itself).
CUE_WORDS = {
    "medications", "medication", "medicines", "allergies", "allergic", "allergy", "vaccines", "vaccine", "vaccinated", "vaccination",
    "prescribed", "prescription", "emergency", "hospitalized", "appointment", "diagnosed", "diagnosis", "diagnoses", "history",
    "immunizations", "immunization", "received", "latest", "recent", "recently", "currently", "problems", "conditions", "trending",
    "visited", "readings", "results", "started", "starting", "taking", "booster", "admitted", "reactions"}

# Ordinary words that sit one letter away from a vocabulary word and must never be 'corrected'.
COMMON = set("""doing being going think about could would there their where which while those these today right still since
after before other again under every never always value values level levels taken takes times thing things things lately
early later later wants given given given years months weeks hours check checked ready shown known start state stated
house cases cause seems looks looked tests total""".split())
class Parser:
    def __init__(self, lexicon: dict):
        self.concepts = {c["key"]: c for c in lexicon["concepts"]}
        # phrase -> concept keys, and first token -> phrases (longest first)
        self.phrases: dict[str, list[str]] = {}
        for c in lexicon["concepts"]:
            for p in c["phrases"]:
                self.phrases.setdefault(p, []).append(c["key"])
        self.by_first: dict[str, list[list[str]]] = {}
        for p in sorted(self.phrases, key=lambda p: (-len(p.split()), -len(p), p)):
            toks = p.split()
            self.by_first.setdefault(toks[0], []).append(toks)
        vocab = {t for p in self.phrases for t in p.split()} | set(CUE_WORDS)
        self.vocab = vocab
        self.fuzzy_pool = sorted(t for t in vocab if len(t) >= 5)
        self._cache: dict[str, str] = {}

    # ---- tokens -----------------------------------------------------------------

    def canon(self, tok: str) -> str:
        """Map a question word onto the vocabulary: exact, then plural, then one typo away."""
        if tok in self._cache:
            return self._cache[tok]
        out = tok
        if tok not in self.vocab and tok not in STOP and tok not in COMMON and not tok.isdigit():
            if tok.endswith("es") and tok[:-2] in self.vocab:
                out = tok[:-2]
            elif tok.endswith("s") and tok[:-1] in self.vocab:
                out = tok[:-1]
            elif len(tok) >= 5:
                best, best_d = None, 2
                for v in self.fuzzy_pool:
                    if abs(len(v) - len(tok)) > 1 or v[0] != tok[0] and v[1:2] != tok[1:2]:
                        continue
                    d = osa_distance(tok, v)
                    if d < best_d or (d == best_d and best is not None and v < best):
                        best, best_d = v, d
                if best is not None and best_d == 1:
                    out = best
        self._cache[tok] = out
        return out

    def mentions(self, toks: list[str]) -> list[dict]:
        """Longest phrase match at each position, left to right, no overlaps."""
        out = []
        i = 0
        while i < len(toks):
            hit = None
            for cand in self.by_first.get(toks[i], []):
                n = len(cand)
                if toks[i:i + n] == cand:
                    hit = cand
                    break
            if hit:
                phrase = " ".join(hit)
                out.append({"start": i, "end": i + len(hit), "phrase": phrase, "keys": self.phrases[phrase]})
                i += len(hit)
            else:
                i += 1
        return out

    # ---- time frame -----------------------------------------------------------------

    @staticmethod
    def window(q: str, as_of: str) -> dict | None:
        y = int(as_of[:4])
        m = re.search(r"\b(?:in|during|for|from|of)?\s*(?:the\s+)?(?:year\s+)?((?:19|20)\d\d)\b", q)
        since = re.search(r"\b(?:since|after)\s+((?:19|20)\d\d)\b", q)
        if since:
            return {"start": f"{since.group(1)}-01-01", "end": as_of, "label": f"since {since.group(1)}"}
        before = re.search(r"\bbefore\s+((?:19|20)\d\d)\b", q)
        if before:
            return {"start": "1900-01-01", "end": f"{int(before.group(1)) - 1}-12-31", "label": f"before {before.group(1)}"}
        if m:
            yr = m.group(1)
            return {"start": f"{yr}-01-01", "end": f"{yr}-12-31", "label": f"in {yr}"}
        n = re.search(r"\b(?:past|last|previous|prior)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+(months?|years?|yrs?|mos?)\b", q)
        if n:
            k = int(n.group(1)) if n.group(1).isdigit() else NUMWORDS[n.group(1)]
            months = k if n.group(2).startswith("mo") else 12 * k
            return {"start": minus_months(as_of, months), "end": as_of, "label": f"in the past {k} {'month' if months == k else 'year'}{'s' if k != 1 else ''}"}
        if re.search(r"\b(?:in|over|during|within|for)\s+the\s+(?:past|last|previous|prior)\s+(?:year|12 months|twelve months)\b|\b(?:this past|the past|past) year\b|\b(?:past|last) 12 months\b|\blast twelve months\b", q):
            return {"start": minus_months(as_of, 12), "end": as_of, "label": "in the past 12 months"}
        if re.search(r"\blast year\b", q):
            return {"start": f"{y - 1}-01-01", "end": f"{y - 1}-12-31", "label": f"in {y - 1}"}
        if re.search(r"\bthis year\b", q):
            return {"start": f"{y}-01-01", "end": as_of, "label": f"in {y}"}
        return None

    # ---- intent -------------------------------------------------------------------------

    def parse(self, question: str, as_of: str) -> dict:
        q = norm(question)
        toks = [self.canon(t) for t in q.split()]
        ms = self.mentions(toks)
        # cue words are read outside the medical terms, so 'allergic rhinitis' or 'sleep apnea' do not trigger them
        covered = {i for m in ms for i in range(m["start"], m["end"])}
        qc = " ".join(t if i not in covered else "_" for i, t in enumerate(toks))
        cue = {k: bool(re.search(p, qc)) for k, p in CUES.items()}
        win = self.window(q, as_of)

        def pick(kinds: tuple[str, ...]) -> str | None:
            """The first mention that has a concept of one of these kinds, in kind-preference order."""
            for m in ms:
                for kind in kinds:
                    for key in m["keys"]:
                        if self.concepts[key]["kind"] == kind:
                            return key
            return None

        def out(intent: str, concept: str | None = None, w: dict | None = win) -> dict:
            return {"intent": intent, "concept": concept, "window": w, "q": q}

        if cue["advice"]:
            return out("advice", w=None)
        if cue["age"] and not ms:
            return out("age", w=None)

        if cue["allergy"]:
            med_allergy_word = any("allerg" in m["phrase"] for m in ms)
            if not (med_allergy_word and cue["med"]):
                key = pick(("allergy", "med", "condition", "obs"))
                return out("allergy_check", key, None) if key else out("allergy_list", w=None)

        if cue["outside"]:
            return out("unsupported", w=None)

        vax = pick(("vaccine",))
        if vax and (cue["vaccine"] or not pick(("condition", "med", "obs"))):
            return out("vaccine_last", vax, None)
        if cue["vaccine"] and not ms and not cue["med"]:
            return out("vaccine_list", w=None)

        if cue["er"]:
            return out("er_visits", w=win or {"start": minus_months(as_of, 12), "end": as_of, "label": "in the past 12 months"})
        if cue["admit"] and not ms:
            return out("admissions", w=win or {"start": minus_months(as_of, 12), "end": as_of, "label": "in the past 12 months"})
        if cue["visit"] and not ms:
            return out("last_visit", w=None)

        # the first medical term decides the subject; cues break ties inside one ambiguous term
        first = None
        for m in ms:
            kinds = {self.concepts[k]["kind"] for k in m["keys"]} & {"med", "condition", "obs"}
            if not kinds:
                continue
            if len(kinds) > 1:
                order = ("med", "condition", "obs") if cue["med"] else ("condition", "obs", "med") if cue["has"] else ("obs", "condition", "med")
                kind = next(k for k in order if k in kinds)
            else:
                kind = kinds.pop()
            first = (kind, next(k for k in m["keys"] if self.concepts[k]["kind"] == kind))
            break

        if first and first[0] == "med":
            if cue["start"] or re.search(r"\bwhen\b", qc):
                return out("med_start", first[1], None)
            return out("on_med", first[1], None)
        if first and first[0] == "condition":
            return out("has_condition", first[1], None)
        if first and first[0] == "obs":
            if win and re.fullmatch(r"in \d{4}", win["label"]):
                return out("latest_value", first[1])
            if cue["trend"] or (cue["trend_weak"] and not cue["latest"]):
                return out("trend", first[1])
            return out("latest_value", first[1])
        if cue["med"]:
            return out("med_list", w=None)
        if cue["problem"]:
            return out("problem_list", w=None)
        if cue["age"]:
            return out("age", w=None)
        return out("unsupported", w=None)


def minus_months(iso: str, months: int) -> str:
    y, m, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
    total = y * 12 + (m - 1) - months
    y2, m2 = divmod(total, 12)
    m2 += 1
    days = [31, 29 if (y2 % 4 == 0 and (y2 % 100 != 0 or y2 % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1]
    return f"{y2:04d}-{m2:02d}-{min(d, days):02d}"
