"""Sanity-check a built font against the upstream Courier Prime release.

usage: verify.py FONT FAMILY STYLE PRIME_TTF CODE_TTF

Fails unless FONT has the given names, the same vertical metrics, advance
widths and character coverage as PRIME_TTF, and its digits are shaped like
CODE_TTF's while its letters are still shaped like PRIME_TTF's, and its
~ is no longer CODE_TTF's (it comes from Hack).
"""

import string
import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

METRICS = {
    "hhea": ["ascent", "descent", "lineGap"],
    "OS/2": ["sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent",
             "usWinDescent", "fsSelection", "usWeightClass"],
    "post": ["isFixedPitch", "italicAngle"],
    "head": ["unitsPerEm", "macStyle"],
}


def bounds(font, char):
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[font.getBestCmap()[ord(char)]].draw(pen)
    return pen.bounds


def distance(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def shaped_like(font, char, ref, other):
    """True if char's bounding box matches ref's better than other's.

    Some designs differ by only a couple of units between the two fonts,
    and converting curves to TrueType moves extremes by about a unit, so
    an absolute tolerance alone can't tell them apart.
    """
    got, want, alt = bounds(font, char), bounds(ref, char), bounds(other, char)
    return distance(got, want) <= 2 and (want == alt or
                                         distance(got, want) < distance(got, alt))


def main(path, family, style, prime_path, code_path):
    font, prime, code = TTFont(path), TTFont(prime_path), TTFont(code_path)
    errors = []

    names = (font["name"].getDebugName(1), font["name"].getDebugName(2))
    if names != (family, style):
        errors.append(f"names are {names}, expected {(family, style)}")

    for table, attrs in METRICS.items():
        for attr in attrs:
            got = getattr(font[table], attr)
            want = getattr(prime[table], attr)
            if got != want:
                errors.append(f"{table}.{attr} is {got}, Prime has {want}")

    widths = {w for w, _ in font["hmtx"].metrics.values()}
    prime_widths = {w for w, _ in prime["hmtx"].metrics.values()}
    if widths != prime_widths:
        errors.append(f"advance widths {sorted(widths)}, "
                      f"Prime has {sorted(prime_widths)}")

    cmap, prime_cmap = set(font.getBestCmap()), set(prime.getBestCmap())
    if cmap != prime_cmap:
        errors.append(f"coverage differs from Prime: "
                      f"missing {sorted(map(hex, prime_cmap - cmap))}, "
                      f"extra {sorted(map(hex, cmap - prime_cmap))}")

    for chars, ref, other, ref_name in [
            (string.digits, code, prime, "Code"),
            (string.ascii_letters, prime, code, "Prime")]:
        for char in chars:
            if not shaped_like(font, char, ref, other):
                errors.append(f"{char!r} is not shaped like {ref_name}'s")

    if distance(bounds(font, "~"), bounds(code, "~")) <= 2:
        errors.append("'~' is still Code's, not Hack's")

    if errors:
        sys.exit(f"{path}:\n  " + "\n  ".join(errors))
    print(f"{path}: OK")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__.split("\n\n")[1])
    main(*sys.argv[1:])
