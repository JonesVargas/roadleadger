from decimal import Decimal, ROUND_HALF_UP

VERSION = "distance_weight_v1"
RATE_PER_KM = Decimal("5")
RATE_PER_MILE = RATE_PER_KM * Decimal("1.609344")
RATE_PER_TON = Decimal("1")

def freight_price(distance_km, weight_tons):
    km, tons = Decimal(str(distance_km)), Decimal(str(weight_tons))
    if not km.is_finite() or not tons.is_finite() or km < 0 or tons < 0:
        raise ValueError("Distância e peso devem ser valores válidos e não negativos.")
    km = km.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    tons = tons.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return (km * RATE_PER_KM + tons * RATE_PER_TON).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
