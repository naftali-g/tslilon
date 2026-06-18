# -*- coding: utf-8 -*-
"""apply_niqqud_fixes.py — consume the decisions JSON from tools/niqqud_review.html and write
corrections straight into the ORIGINAL lexicon sources, transactionally, then rebuild.

Decisions JSON (exported by the review page):
  {"fixes": [{"old": "...", "new": "...", "cat": "noun|adjective|verb", "role": "..."}, ...],
   "accepted": ["<form confirmed correct>", ...]}

Safety design (after adversarial review):
  - Validate the whole payload first; reject quotes/backslashes; skip no-ops; abort on fix-chains.
  - JSON sources (generated_lexicon*.json) are PARSED and patched at the exact section+field+entry,
    so escaping is correct by construction and a homograph (same spelling, different part of
    speech) is never broadcast. Re-serialized to match the source's own indent/ascii style.
  - words_extra.py uses a guarded single-occurrence quoted replacement (refuses if ambiguous).
  - All edits are staged in memory and written all-or-nothing (temp + os.replace); if the
    rebuild fails, every source and the accepted list are restored.

Usage:  python3 tools/apply_niqqud_fixes.py ~/Downloads/niqqud_decisions.json [--no-build]
"""
import glob
import json
import os
import re
import subprocess
import sys
import unicodedata
from typing import NoReturn

HERE = os.path.dirname(os.path.abspath(__file__))
ACCEPTED = os.path.join(HERE, "niqqud_accepted.json")
GEN = sorted(glob.glob(os.path.join(HERE, "generated_lexicon*.json")))
EXTRA = os.path.join(HERE, "words_extra.py")
SECTION = {"noun": "nouns", "adjective": "adjectives", "verb": "verbs"}


def die(msg) -> NoReturn:
    print("ERROR:", msg)
    sys.exit(2)


def validate(fixes, accepted):
    if not isinstance(fixes, list):
        die("'fixes' must be a list of {old,new,cat,role} objects")
    if not isinstance(accepted, list) or any(not isinstance(a, str) for a in accepted):
        die("'accepted' must be a list of strings")
    clean = []
    for f in fixes:
        if not isinstance(f, dict):
            die(f"fix is not an object: {f!r}")
        old, new, cat, role = f.get("old"), f.get("new"), f.get("cat"), f.get("role")
        if not (isinstance(old, str) and isinstance(new, str) and isinstance(cat, str) and isinstance(role, str)
                and old.strip() and new.strip() and cat.strip() and role.strip()):
            die(f"fix has a missing/non-string field: {f!r}")
        if any(ch in old or ch in new for ch in ('"', "\\")):
            die(f"fix contains a quote or backslash (refused): {f!r}")
        if cat not in SECTION:
            die(f"fix has unknown cat {cat!r}: {f!r}")
        if old == new:
            print(f"  · skip no-op: {old}")
            continue
        # Nakdan output isn't always NFC; our lexicon is — normalize at the write boundary so the
        # corrected forms match the rest of the data (and pass the test_lexicon NFC gate).
        clean.append({"old": old, "new": unicodedata.normalize("NFC", new), "cat": cat, "role": role})
    chain = {f["old"] for f in clean} & {f["new"] for f in clean}
    if chain:
        die(f"fix chain (a 'new' is also an 'old'): {chain} — resolve before applying")
    return clean


def dump_like(original, obj):
    """Serialize obj matching original's indent / ascii-escaping / trailing newline (minimal diff)."""
    ascii_mode = "\\u" in original
    if "\n" not in original.strip():
        s = json.dumps(obj, ensure_ascii=ascii_mode, separators=(",", ":"))
    else:
        m = re.search(r"\n( +)\S", original)
        s = json.dumps(obj, ensure_ascii=ascii_mode, indent=len(m.group(1)) if m else 2)
    if original.endswith("\n") and not s.endswith("\n"):
        s += "\n"
    return s


def main():
    argv = sys.argv[1:]
    no_build = "--no-build" in argv
    argv = [a for a in argv if not a.startswith("--")]
    if not argv:
        die("usage: apply_niqqud_fixes.py <decisions.json> [--no-build]")
    dec = json.load(open(argv[0], encoding="utf-8"))
    accepted_in = dec.get("accepted", []) or []
    fixes = validate(dec.get("fixes", []) or [], accepted_in)
    print(f"validated {len(fixes)} fix(es), {len(accepted_in)} accepted-as-is")

    snap = {p: open(p, encoding="utf-8").read() for p in GEN + ([EXTRA] if os.path.exists(EXTRA) else [])}
    gen_obj = {p: json.loads(snap[p]) for p in GEN}
    extra_txt = snap.get(EXTRA)

    applied, missing, changed = [], [], set()
    for fx in fixes:
        old, new = fx["old"], fx["new"]
        field = "w" if fx["cat"] == "noun" else fx["role"]   # ms/fs/mp/fp for adj/verb
        hit = 0
        for p in GEN:                                         # entry-aware: only this section's field
            for e in gen_obj[p].get(SECTION[fx["cat"]], []):
                if e.get(field) == old:
                    e[field] = new
                    hit += 1
                    changed.add(p)
        if not hit and extra_txt is not None:                # guarded fallback for words_extra.py
            occ = extra_txt.count('"' + old + '"') + extra_txt.count("'" + old + "'")
            if occ == 1:
                extra_txt = extra_txt.replace('"' + old + '"', '"' + new + '"').replace("'" + old + "'", "'" + new + "'")
                hit = 1
            elif occ > 1:
                print(f"  ⚠ {old}: {occ} occurrences in words_extra.py — ambiguous, edit by hand")
        if hit:
            applied.append(fx)
            print(f"  ✓ [{fx['cat']}/{fx['role']}] {old} -> {new}  ({hit}×)")
        else:
            missing.append(fx)
            print(f"  ⚠ [{fx['cat']}/{fx['role']}] {old} not found in sources — skipped")

    staged = {p: dump_like(snap[p], gen_obj[p]) for p in changed}   # only files we actually edited
    if extra_txt is not None and extra_txt != snap[EXTRA]:
        staged[EXTRA] = extra_txt

    if not staged and not accepted_in:
        print("nothing to write."); return

    written = []
    try:
        for p, txt in staged.items():
            tmp = p + ".tmp"
            open(tmp, "w", encoding="utf-8").write(txt)
            os.replace(tmp, p)
            written.append(p)
    except Exception as e:
        for p in written:
            open(p, "w", encoding="utf-8").write(snap[p])
        die(f"write failed — restored sources: {e!r}")

    acc_before = sorted(set(json.load(open(ACCEPTED, encoding="utf-8")))) if os.path.exists(ACCEPTED) else []
    acc = (set(acc_before) | set(accepted_in) | {f["new"] for f in applied}) - {f["old"] for f in applied}
    json.dump(sorted(acc), open(ACCEPTED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if no_build:
        print(f"staged {len(written)} file(s); skipped rebuild (--no-build)."); return
    print("rebuilding lexicon (merge_lexicon + build_lexicon)...")
    try:
        subprocess.run([sys.executable, os.path.join(HERE, "merge_lexicon.py")], check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, os.path.join(HERE, "build_lexicon.py")], check=True, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        for p in written:                                    # roll back sources + accepted
            open(p, "w", encoding="utf-8").write(snap[p])
        json.dump(acc_before, open(ACCEPTED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        die(f"rebuild failed — rolled back all changes: {e!r}")
    print(f"done. {len(applied)} fix(es) across {len(written)} file(s)"
          + (f", {len(missing)} skipped" if missing else "")
          + ". Re-run tools/audit_niqqud.py to confirm; tools/test_lexicon.py to gate.")


if __name__ == "__main__":
    main()
