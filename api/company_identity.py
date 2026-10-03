"""Game-only company identifier; never a valid Brazilian taxpayer ID."""
from uuid import UUID


def fictitious_cnpj(company_id: UUID) -> str:
    base = f"99{company_id.int % 10**10:010d}"
    weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(int(digit) * weight for digit, weight in zip(base, weights))
    remainder = total % 11
    actual_first = 0 if remainder < 2 else 11 - remainder
    # Deliberately wrong first check digit so it cannot identify a real company.
    digits = base + str((actual_first + 1) % 10) + "0"
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
