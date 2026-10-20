import numpy as np

from bph_app.counter_code import STRIP_H, decode_gray, encode_strip


def test_roundtrip_and_corruption() -> None:
    for n in (0, 1, 2500, 134999, (1 << 20) - 1):
        img = np.full((360, 640), 90, np.uint8)
        img[: 2 * STRIP_H] = encode_strip(n, 640)
        assert decode_gray(img) == n
    img[STRIP_H:2 * STRIP_H] = img[:STRIP_H]   # rangées non complémentaires : image rejetée
    assert decode_gray(img) is None
    assert decode_gray(np.full((360, 640), 90, np.uint8)) is None
