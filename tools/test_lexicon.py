# -*- coding: utf-8 -*-
"""
test_lexicon.py — OFFLINE verification (NOT shipped). Phoneme model.

(1) DATA INTEGRITY: independently recompute each word's PHONEME position index
    from its vocalized form and compare to what build_lexicon.py baked in.
(2) CONSTRAINT: generate sentences for every (phoneme x position) cell and assert
    every word is >=3 words and actually carries the target SOUND at the chosen
    position (re-derived independently from the niqqud).

Run:  python3 tools/test_lexicon.py
"""
import json, os, random, sys

random.seed(42)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEX = json.load(open(os.path.join(ROOT, "lexicon.json"), encoding="utf-8"))

FOLD = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
DAG, SHIN, SIN, HIRIQ, TSERE = "ּ", "ׁ", "ׂ", "ִ", "ֵ"
VOWELP = {chr(c) for c in range(0x05B0, 0x05BC)} | {chr(0x05C7)}
def isniq(c): return "֑" <= c <= "ׇ"
def heb(c): return "א" <= c <= "ת"
SIMPLE = {"ס": "S", "ת": "T", "ט": "T", "ק": "K", "ח": "X", "ג": "G", "ד": "D",
          "ז": "Z", "ל": "L", "מ": "M", "נ": "N", "צ": "TS", "ר": "R", "א": "GLOTTAL", "ע": "GLOTTAL"}
PHON = ["GLOTTAL", "B", "V", "G", "D", "H", "Z", "X", "T", "Y", "K", "L", "M", "N", "S", "P", "F", "TS", "R", "SH"]
POS = ["FIRST", "MIDDLE", "LAST"]
GN = {"ms": ("m", "sg"), "fs": ("f", "sg"), "mp": ("m", "pl"), "fp": ("f", "pl")}

PASS = [0]; FAILS = []
def check(c, m): (PASS.__setitem__(0, PASS[0] + 1) if c else FAILS.append(m))


def sound_of(base, m, is_first, is_last, prev):
    if base == "ב": return "B" if DAG in m else "V"
    if base == "כ": return "K" if DAG in m else "X"
    if base == "פ": return "P" if DAG in m else "F"
    if base == "ש": return "SH" if SHIN in m else ("S" if SIN in m else None)
    if base in SIMPLE: return SIMPLE[base]
    if base == "ה": return None if (is_last and DAG not in m) else "H"
    if base == "ו":
        if ("ֹ" in m) or ("ֺ" in m): return None
        if DAG in m: return None
        if VOWELP & set(m): return "V"
        return "V" if is_first else None
    if base == "י":
        if VOWELP & set(m): return "Y"
        if is_first: return "Y"
        if (HIRIQ in prev) or (TSERE in prev): return None
        return "Y"
    return None


def pidx(w):
    """Independent phoneme index {phoneme: sorted[positions]}."""
    ch = list(w); n = len(ch); idx = {}; i = 0; prev = ""
    while i < n:
        base = FOLD.get(ch[i], ch[i])
        if not heb(base): i += 1; continue
        j = i + 1; mk = ""
        while j < n and isniq(ch[j]): mk += ch[j]; j += 1
        s = sound_of(base, mk, i == 0, j >= n, prev)
        if s:
            pos = "FIRST" if i == 0 else ("LAST" if j >= n else "MIDDLE")
            idx.setdefault(s, set()).add(pos)
        prev = mk; i = j
    return {k: sorted(v) for k, v in idx.items()}


def eq(a, b):
    if sorted(a) != sorted(b): return False
    return all(sorted(a[k]) == sorted(b[k]) for k in a)


# ---- (1) integrity: stored idx == independent recompute ----
for e in LEX["nouns"]:
    check(eq(pidx(e["w"]), e["idx"]), f"noun idx mismatch: {e['w']}")
for kind in ("adjectives", "verbs"):
    for e in LEX[kind]:
        for k in GN:
            f = e["forms"][k]
            check(eq(pidx(f["w"]), f["idx"]), f"{kind} idx mismatch: {f['w']}")


# ---- engine (mirrors the in-page JS; matches on the stored phoneme idx) ----
def mpos(idx, ph, ps): return ph in idx and any(x in ps for x in idx[ph])
def gnf(nn): return nn["g"] + "-" + nn["n"]


def candidates(ph, ps):
    nouns = [e for e in LEX["nouns"] if mpos(e["idx"], ph, ps)]
    adj = {}; verb = {}
    for e in LEX["adjectives"]:
        for k in GN:
            if mpos(e["forms"][k]["idx"], ph, ps):
                adj.setdefault("-".join(GN[k]), []).append(e["forms"][k]["w"])
    for e in LEX["verbs"]:
        for k in GN:
            if mpos(e["forms"][k]["idx"], ph, ps):
                verb.setdefault("-".join(GN[k]), []).append((e["forms"][k]["w"], e["trans"]))
    return nouns, adj, verb


def build_sentence(ph, ps):
    nouns, adj, verb = candidates(ph, ps)
    ns = nouns[:]; random.shuffle(ns)
    for subj in ns:
        gn = "-".join((subj["g"], subj["n"]))
        adjs = adj.get(gn, []); verbs = verb.get(gn, [])
        tverbs = [w for (w, tr) in verbs if tr]
        objs = [o["w"] for o in nouns if o["w"] != subj["w"]]
        for t in random.sample(["A", "C", "B", "D"], 4):
            if t == "A" and adjs and verbs: return [subj["w"], random.choice(adjs), random.choice(verbs)[0]]
            if t == "C" and adjs and tverbs and objs: return [subj["w"], random.choice(adjs), random.choice(tverbs), random.choice(objs)]
            if t == "B" and tverbs and objs: return [subj["w"], random.choice(tverbs), random.choice(objs)]
            if t == "D" and tverbs and objs:
                obj = random.choice(objs)
                oe = next(o for o in nouns if o["w"] == obj)
                oadj = [a for a in adj.get("-".join((oe["g"], oe["n"])), []) if a != obj]
                if oadj: return [subj["w"], random.choice(tverbs), obj, random.choice(oadj)]
    return None


def generate(ph, ps, n):
    out, seen, att = [], set(), 0
    while len(out) < n and att < max(800, n * 200):
        att += 1
        s = build_sentence(ph, ps)
        if not s: break
        if len(set(s)) != len(s): continue
        key = " ".join(s)
        if key in seen: continue
        seen.add(key); out.append(s)
    return out


# ---- (2) constraint across every cell ----
feasible, total = 0, 0
for ph in PHON:
    for P in POS:
        sents = generate(ph, [P], 10)
        if sents: feasible += 1
        for words in sents:
            total += 1
            check(len(words) >= 3, f"<3 words: {' '.join(words)}")
            for w in words:
                check(P in pidx(w).get(ph, []), f'word "{w}" lacks /{ph}/ at {P}')

# multi-position unions
for ph, ps in [("SH", ["FIRST", "LAST"]), ("X", ["FIRST", "MIDDLE", "LAST"])]:
    for words in generate(ph, ps, 8):
        for w in words:
            check(any(p in pidx(w).get(ph, []) for p in ps), f'multi "{w}" not /{ph}/@{ps}')

print("=" * 60)
print("PHONEME LEXICON / ENGINE VERIFICATION")
print("=" * 60)
print(f"  feasible cells   : {feasible}/{len(PHON)*3}")
print(f"  sentences checked: {total}")
print(f"  assertions       : {PASS[0]} passed, {len(FAILS)} failed")
for m in FAILS[:20]: print("   -", m)
print("\n  samples:")
for ph, P in [("K", "FIRST"), ("X", "MIDDLE"), ("S", "FIRST"), ("T", "LAST"), ("V", "MIDDLE")]:
    print(f"   /{ph}/ {P}:  " + "  |  ".join(" ".join(x) for x in generate(ph, [P], 3)))
sys.exit(1 if FAILS else 0)
