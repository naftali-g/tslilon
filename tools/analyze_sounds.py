# -*- coding: utf-8 -*-
"""
analyze_sounds.py — OFFLINE diagnostic (NOT shipped).

Reuses the CANONICAL phoneme logic from build_lexicon.py (imports its sound_of /
coverage — no duplicated rules) to report:
  - the phoneme x position coverage matrix
  - a matres/silent sanity check: how often ו/י/ה are classified consonant vs
    vowel/silent. Handy when expanding the lexicon — confirms the heuristic stays
    sane (e.g. vav should be mostly vowel, final he mostly silent).

Run:  python3 tools/analyze_sounds.py
"""
import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_lexicon as B  # noqa: E402

lex = B.build()

# every vocalized surface form
forms = [e["w"] for e in lex["nouns"]]
for kind in ("adjectives", "verbs"):
    for e in lex[kind]:
        forms += [e["forms"][k]["w"] for k in ("ms", "fs", "mp", "fp")]


def isniq(c): return "֑" <= c <= "ׇ"
def heb(c): return "א" <= c <= "ת"


# matres / silent sanity — classify each ו/י/ה occurrence via the canonical B.sound_of
mat = collections.Counter()
WATCH = {"ו", "י", "ה"}
for w in forms:
    ch = list(w); n = len(ch); i = 0; prev = ""
    while i < n:
        base = B.FOLD.get(ch[i], ch[i])
        if not heb(base):
            i += 1
            continue
        j = i + 1; mk = ""
        while j < n and isniq(ch[j]):
            mk += ch[j]
            j += 1
        if base in WATCH:
            s = B.sound_of(base, mk, i == 0, j >= n, prev)
            mat[f"{base} -> {s or 'vowel/silent'}"] += 1
        prev = mk
        i = j

matrix = B.coverage(lex)
feasible = sum(1 for v in matrix.values() if v["ok"])

print("=" * 64)
print("PHONEME COVERAGE  (sound_of/coverage imported from build_lexicon.py)")
print("=" * 64)
print(f"  {'sound':9}{'letters':9}{'FIRST':>13}{'MIDDLE':>13}{'LAST':>13}")
for ph in B.PHONEMES:
    cells = []
    for P in B.POSITIONS:
        c = matrix[(ph, P)]
        cells.append(f"{'OK ' if c['ok'] else '-- '}{c['n']}n{c['a']}a{c['v']}v")
    print(f"  {ph:9}{B.SOURCES[ph]:9}{cells[0]:>13}{cells[1]:>13}{cells[2]:>13}")
print(f"\n  feasible: {feasible}/{len(matrix)}   dead:",
      ", ".join(f"{ph}/{P}" for (ph, P), v in matrix.items() if not v["ok"]))

print("\n" + "=" * 64)
print("MATRES / SILENT SANITY  (ו/י/ה consonant vs vowel)")
print("=" * 64)
for k in sorted(mat):
    print(f"  {k:22} {mat[k]}")
