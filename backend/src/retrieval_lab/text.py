from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have
    having he her here hers herself him himself his how i if in into is it its itself just me more most
    my myself no nor not now of off on once only or other our ours ourselves out over own same she
    should so some such than that the their theirs them themselves then there these they this those
    through to too under until up very was we were what when where which while who whom why will with
    would you your yours yourself yourselves according says say said text book author describe
    described explain explains tell does mean means many much one also upon thus shall may might must
    yet because possible therefore however whether yes
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[\"'“‘(\[]*[A-Z0-9])")
_CITATION = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text)
    folded = folded.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(folded.split())


def stem(token: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)] + ("y" if suffix in {"ies", "ied"} else "")
    return token


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text).lower())


def content_terms(text: str) -> list[str]:
    return [stem(t) for t in tokens(text) if t not in STOPWORDS and len(t) > 1]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(normalize(text)) if s.strip()]


def strip_citations(text: str) -> str:
    return _CITATION.sub("", text).strip()


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
