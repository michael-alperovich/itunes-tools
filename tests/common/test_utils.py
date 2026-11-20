import pytest

from itunes_tools.common.utils import from_persistent_id, to_persistent_id

# (high, low) as COM returns them (signed 32-bit), and the matching hex persistent ID.
PERSISTENT_ID_CASES = [
    pytest.param(0, 0, "0000000000000000", id="zero"),
    pytest.param(0x1A2B3C4D, 0x5E6F7081, "1A2B3C4D5E6F7081", id="positive-halves"),
    pytest.param(-1, -1, "FFFFFFFFFFFFFFFF", id="negative-halves"),
    pytest.param(-2147483648, 2147483647, "800000007FFFFFFF", id="int32-limits"),
]


@pytest.mark.parametrize(("high", "low", "persistent_id"), PERSISTENT_ID_CASES)
def test_to_persistent_id_returns_16_digit_uppercase_hex(high, low, persistent_id):
    assert to_persistent_id(high, low) == persistent_id


@pytest.mark.parametrize(("high", "low", "persistent_id"), PERSISTENT_ID_CASES)
def test_from_persistent_id_returns_signed_halves(high, low, persistent_id):
    assert from_persistent_id(persistent_id) == (high, low)


def test_from_persistent_id_accepts_lowercase_hex():
    assert from_persistent_id("1a2b3c4d5e6f7081") == (0x1A2B3C4D, 0x5E6F7081)


def test_from_persistent_id_rejects_non_hex():
    with pytest.raises(ValueError):
        from_persistent_id("not-a-hex-id")
