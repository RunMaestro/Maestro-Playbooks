#!/usr/bin/env python3
"""A stand-in for `qmd` in test_install_memory.py: collection add/list/show/remove, update, embed, search.
State in $QMD_STUB_STATE (JSON). Not part of an install."""
import json, os, sys
from pathlib import Path
st = Path(os.environ["QMD_STUB_STATE"])
cols = json.loads(st.read_text()) if st.exists() else {}
a = sys.argv[1:]
if a[:2] == ["collection", "list"]:
    print("\n".join(f"{n} (qmd://{n}/)" for n in cols))
elif a[:2] == ["collection", "show"]:
    if a[2] in cols:
        print(f"Collection: {a[2]}\n  Path:     {cols[a[2]]}")
    else:
        sys.exit(1)
elif a[:2] == ["collection", "add"]:
    cols[a[a.index("--name") + 1]] = str(Path(a[2]).resolve())
elif a[:2] == ["collection", "remove"]:
    cols.pop(a[2], None)
elif a and a[0] == "search":
    print(f"qmd://{a[a.index('-c') + 1]}/MEMORY.md:1")
st.write_text(json.dumps(cols))
