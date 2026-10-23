from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from PIL import Image


def _bits_to_hex(bits) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
    return f"{value:016x}"


def _ahash(image: Image.Image) -> str:
    gray = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    values = list(gray.getdata())
    average = sum(values) / 64
    return _bits_to_hex(value >= average for value in values)


def _dhash(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    values = list(gray.getdata())
    bits = []
    for row_index in range(8):
        row = values[row_index * 9 : (row_index + 1) * 9]
        bits.extend(row[index] > row[index + 1] for index in range(8))
    return _bits_to_hex(bits)


def _distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: verifier MANIFEST IMAGE_ROOT")

    manifest = Path(sys.argv[1])
    image_root = Path(sys.argv[2])
    rows = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 65:
        raise SystemExit(f"expected 65 backup fingerprints, got {len(rows)}")

    max_ahash = 0
    max_dhash = 0
    for index, raw in enumerate(rows, 1):
        rel, width, height, expected_ahash, expected_dhash = raw.split(",")
        image_path = image_root / rel
        payload = image_path.read_bytes()
        with Image.open(BytesIO(payload)) as image:
            expected_size = (int(width), int(height))
            if image.size != expected_size:
                raise SystemExit(
                    f"dimension mismatch {rel}: backup={expected_size[0]}x{expected_size[1]} "
                    f"candidate={image.width}x{image.height}"
                )
            ahash_distance = _distance(expected_ahash, _ahash(image))
            dhash_distance = _distance(expected_dhash, _dhash(image))

        max_ahash = max(max_ahash, ahash_distance)
        max_dhash = max(max_dhash, dhash_distance)
        print(f"{index:02d}/65 {rel} ahash={ahash_distance} dhash={dhash_distance}")

        if ahash_distance > 8 or dhash_distance > 12:
            raise SystemExit(
                f"visual fingerprint mismatch {rel}: "
                f"ahash={ahash_distance} dhash={dhash_distance}"
            )

    print(
        "VERIFIED_TUTORIAL_SCREENSHOTS=65 "
        f"MAX_AHASH_DISTANCE={max_ahash} MAX_DHASH_DISTANCE={max_dhash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
