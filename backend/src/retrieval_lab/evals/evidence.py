from __future__ import annotations

import unicodedata

_FOLD = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "*": None, "_": None})


def _fold(text: str) -> tuple[str, list[int]]:
    """Lowercase, fold punctuation variants and collapse whitespace, keeping an index map."""
    chars: list[str] = []
    origin: list[int] = []
    previous_space = True
    for index, char in enumerate(text):
        folded = unicodedata.normalize("NFKC", char).translate(_FOLD).lower()
        for piece in folded:
            if piece.isspace():
                if previous_space:
                    continue
                piece = " "
                previous_space = True
            else:
                previous_space = False
            chars.append(piece)
            origin.append(index)
    while chars and chars[-1] == " ":
        chars.pop()
        origin.pop()
    return "".join(chars), origin


def locate(document: str, evidence: str) -> tuple[int, int] | None:
    """Find `evidence` in `document`, tolerant of whitespace, quotes and emphasis markers."""
    needle, _ = _fold(evidence)
    if not needle:
        return None
    haystack, origin = _fold(document)
    position = haystack.find(needle.strip())
    if position == -1:
        return None
    end = position + len(needle.strip()) - 1
    return origin[position], origin[end] + 1
