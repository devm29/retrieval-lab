import pytest

from retrieval_lab.evals.kappa import cohens_kappa, confusion_matrix, interpret_kappa, percent_agreement


def test_perfect_agreement() -> None:
    labels = ["yes", "no", "yes", "no"]
    assert cohens_kappa(labels, labels) == pytest.approx(1.0)


def test_textbook_example() -> None:
    # Wikipedia's worked example: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> kappa 0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert percent_agreement(a, b) == pytest.approx(0.7)
    assert cohens_kappa(a, b) == pytest.approx(0.4)


def test_systematic_disagreement_is_negative() -> None:
    assert cohens_kappa(["y", "n", "y", "n"], ["n", "y", "n", "y"]) == pytest.approx(-1.0)


def test_single_label_everywhere_is_perfect() -> None:
    assert cohens_kappa(["y", "y"], ["y", "y"]) == 1.0


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        cohens_kappa(["y"], ["y", "n"])


def test_confusion_matrix_counts_pairs() -> None:
    assert confusion_matrix(["y", "y", "n"], ["y", "n", "n"]) == {("y", "y"): 1, ("y", "n"): 1, ("n", "n"): 1}


@pytest.mark.parametrize(
    ("kappa", "label"), [(-0.1, "poor"), (0.15, "slight"), (0.5, "moderate"), (0.9, "almost perfect")]
)
def test_interpretation_bands(kappa: float, label: str) -> None:
    assert interpret_kappa(kappa) == label
