"""tools/preview.html carries runtime/beanfx.js inline (a page opened from disk cannot import a module). This checks
the copy between its RUNTIME START and RUNTIME END markers is the runtime with `export ` removed.

    python3 <skill>/tests/test_preview.py           # exits 0 when they match
    python3 <skill>/tests/test_preview.py --write   # copy the runtime in again after changing it
"""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PAGE = SKILL / "tools" / "preview.html"
START, END = "// RUNTIME START\n", "// RUNTIME END\n"


def main():
    page = PAGE.read_text()
    want = (SKILL / "runtime" / "beanfx.js").read_text().replace("export ", "")
    a, b = page.index(START) + len(START), page.index(END)
    if page[a:b] == want:
        print("test_preview: 0 problems")
        return 0
    if "--write" in sys.argv:
        PAGE.write_text(page[:a] + want + page[b:])
        print("test_preview: runtime copied into tools/preview.html")
        return 0
    print("tools/preview.html: the inlined runtime differs from runtime/beanfx.js; run with --write")
    print("test_preview: 1 problems")
    return 1


if __name__ == "__main__":
    sys.exit(main())
