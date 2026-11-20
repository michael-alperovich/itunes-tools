UINT32_MASK = 0xFFFFFFFF
INT32_SIGN_BIT = 0x80000000
UINT32_MOD = 0x100000000
# COM's ``long`` is a signed 32-bit integer.
INT32_MIN = -0x80000000
INT32_MAX = 0x7FFFFFFF


def to_persistent_id(high: int, low: int) -> str:
    """Combine COM's signed 32-bit halves into a 16-digit hex persistent ID."""
    combined = ((high & UINT32_MASK) << 32) | (low & UINT32_MASK)
    return f"{combined:016X}"


def from_persistent_id(persistent_id: str) -> tuple[int, int]:
    """Split a hex persistent ID into signed (high, low) halves for COM calls."""
    combined = int(persistent_id, 16)
    high, low = combined >> 32, combined & UINT32_MASK
    # Convert each half back to signed: values above 0x7FFFFFFF become negative.
    if high & INT32_SIGN_BIT:
        high -= UINT32_MOD
    if low & INT32_SIGN_BIT:
        low -= UINT32_MOD
    return high, low
