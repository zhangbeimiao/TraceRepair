def apply_discount(total: float, rate: float) -> float:
    """Return the price remaining after a fractional discount."""

    if total < 0:
        raise ValueError("total must not be negative")
    if not 0 <= rate <= 1:
        raise ValueError("rate must be between zero and one")
    return round(total * rate, 2)
