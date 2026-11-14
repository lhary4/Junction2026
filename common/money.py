"""Money in words: amounts travel as whole cents (minor units), and a person reads "EUR 1,783.15"."""


def money(minor: int, currency: str = "EUR") -> str:
    return f"{currency} {minor / 100:,.2f}"
