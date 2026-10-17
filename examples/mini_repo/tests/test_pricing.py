import pytest

from minimath import apply_discount


def test_apply_discount_returns_remaining_price() -> None:
    assert apply_discount(200.0, 0.25) == 150.0


def test_apply_discount_validates_inputs() -> None:
    with pytest.raises(ValueError):
        apply_discount(-1.0, 0.25)
    with pytest.raises(ValueError):
        apply_discount(10.0, 1.1)
