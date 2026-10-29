from app.kernel_transport_registry_v209 import apply_kernel_transport_registry_v209
from app import spoof_wireguard_egress_v219 as v219


def main():
    apply_kernel_transport_registry_v209()
    assert v219.VERSION == 219
    assert v219.IRAN_ALLOWED_IPS
    print("SPOOF_WIREGUARD_EGRESS_V219_OK")


if __name__ == "__main__":
    main()
