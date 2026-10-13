from __future__ import annotations

from app.discount_schema import ensure_discount_schema


def main() -> None:
    state = ensure_discount_schema()
    print(
        "DISCOUNT_SCHEMA_READY "
        f"discount_codes={state['discount_codes']} "
        f"discount_redemptions={state['discount_redemptions']}"
    )


if __name__ == "__main__":
    main()
