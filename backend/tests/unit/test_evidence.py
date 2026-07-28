from retrieval_lab.evals.evidence import locate

DOC = "Intro.\n\nThe *Moral Law* causes the people to be in complete\naccord with their ruler’s will.  End."


def test_locate_tolerates_whitespace_quotes_and_emphasis() -> None:
    found = locate(DOC, "The Moral Law causes the people to be in complete accord with their ruler's will.")
    assert found is not None
    start, end = found
    assert DOC[start:end].startswith("The *Moral Law*")
    assert DOC[start:end].endswith("will.")


def test_locate_returns_none_when_absent() -> None:
    assert locate(DOC, "something that is not there") is None


def test_locate_is_case_insensitive() -> None:
    assert locate(DOC, "INTRO.") == (0, 6)
