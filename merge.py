"""Make a Courier Prime master use Courier Prime Code's digits and symbols.

usage: merge.py PRIME_UFO CODE_UFO OUT_UFO FAMILY_NAME

Glyphs swapped: every glyph mapped to a digit (N*), punctuation (P*) or
currency/math/other symbol (Sc, Sm, So) code point, plus the ASCII
modifier symbols ^ and `, plus unencoded variants of those (period.squat,
emdash.alt1, ...). Accents (the other Sk characters) are left alone.

Everything else (metrics, features, names, widths, code points) stays as
Courier Prime, so the result is still strictly monospaced:
- Prime's advance width is kept. Code's alternates that differ in width
  (ellipsis.alt*, emdash.alt*) have the same outlines, only Prime
  normalised them to one cell.
- Glyphs that Code draws as empty (its minute/second are placeholders)
  keep Prime's outline.
- Prime glyphs that are not swapped but use a swapped glyph as a component
  (e.g. ldot uses periodcentered) are decomposed first, so they look
  exactly as before.
- Swapped glyphs that use an unswapped Code glyph as a component (e.g. won
  uses W) are decomposed, so Prime's letters never leak into them.
"""

import sys
import unicodedata

import ufoLib2
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen

SWAP_CATEGORIES = {"Nd", "Nl", "No", "Pc", "Pd", "Pe", "Pf", "Pi", "Po", "Ps",
                   "Sc", "Sm", "So"}
SWAP_EXTRA = {"^", "`"}


def wants_swap(glyph):
    return any(unicodedata.category(chr(u)) in SWAP_CATEGORIES
               or chr(u) in SWAP_EXTRA for u in glyph.unicodes)


def depends_on(font, name, targets, seen=()):
    """True if glyph `name` uses any of `targets`, directly or nested."""
    for comp in font[name].components:
        base = comp.baseGlyph
        if base in targets or (base not in seen and
                               depends_on(font, base, targets, seen + (name,))):
            return True
    return False


def decompose_where(glyph, glyph_set, should_decompose):
    """Replace components matching `should_decompose` with their outlines."""
    keep = []
    for comp in glyph.components:
        if should_decompose(comp.baseGlyph):
            pen = DecomposingRecordingPen(glyph_set)
            glyph_set[comp.baseGlyph].draw(pen)
            pen.replay(TransformPen(glyph.getPen(), comp.transformation))
        else:
            keep.append(comp)
    glyph.components[:] = keep


def main(prime_path, code_path, out_path, family):
    prime = ufoLib2.Font.open(prime_path)
    code = ufoLib2.Font.open(code_path)

    encoded = {g.name for g in prime if g.name in code and wants_swap(g)}
    swap = {g.name for g in prime
            if g.name in code and (g.name in encoded
                                   or g.name.split(".")[0] in encoded)}

    empty = {n for n in swap
             if code[n].getBounds(code) is None
             and prime[n].getBounds(prime) is not None}
    swap -= empty

    # Unswapped Prime glyphs built from swapped ones: freeze their outlines
    # while the originals are still in place. Work from an untouched copy so
    # nested components are drawn from the original shapes.
    original = ufoLib2.Font.open(prime_path)
    frozen = sorted(g.name for g in prime
                    if g.name not in swap and depends_on(prime, g.name, swap))
    for name in frozen:
        decompose_where(prime[name], original,
                        lambda base: base in swap
                        or depends_on(original, base, swap))

    for name in sorted(swap):
        src, dst = code[name], prime[name]
        dst.clearContours()
        dst.clearComponents()
        dst.anchors.clear()
        dst.guidelines.clear()
        src.draw(dst.getPen())
        decompose_where(dst, code, lambda base: base not in swap)

    prime.info.familyName = family
    prime.save(out_path, overwrite=True)

    print(f"{out_path}: swapped {len(swap)} glyphs:")
    print("  " + " ".join(sorted(swap)))
    print(f"  kept from Prime (empty in Code): {' '.join(sorted(empty)) or '-'}")
    print(f"  not in Code: "
          f"{' '.join(sorted(g.name for g in prime if g.name not in code and wants_swap(g))) or '-'}")
    print(f"  decomposed to keep Prime's look: {' '.join(frozen) or '-'}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__.split("\n\n")[1])
    main(*sys.argv[1:])
