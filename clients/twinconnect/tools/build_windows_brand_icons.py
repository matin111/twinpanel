"""Generate Windows brand icons from the user-approved TwinConnect artwork.

Runs after `flutter create --platforms=windows`, before the native Windows build.
Never modifies account branding, VPN engines, subscription data or configuration.
"""
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "branding" / "twinconnect_approved_128.webp"
GENERATED = ROOT / "branding" / "generated"
FLUTTER_ICON = ROOT / "windows" / "runner" / "resources" / "app_icon.ico"


def main() -> None:
    if not SOURCE.is_file() or not FLUTTER_ICON.parent.is_dir():
        raise SystemExit("TwinConnect branding asset or Flutter runner is missing")
    GENERATED.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as approved:
        artwork = approved.convert("RGBA")
        if artwork.size != (128, 128):
            raise SystemExit("Unexpected approved TwinConnect logo dimensions")
        # Preserve the approved artwork; adapt it for Windows icon resolutions.
        icon = artwork.resize((256, 256), Image.Resampling.LANCZOS)
        icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48),
                      (64, 64), (128, 128), (256, 256)]
        icon.save(FLUTTER_ICON, format="ICO", sizes=icon_sizes)
        icon.save(GENERATED / "twinconnect.ico", format="ICO", sizes=icon_sizes)
        icon.save(GENERATED / "twinconnect.png", format="PNG", optimize=True)

        # Two image assets shown on the native Inno Setup installer wizard.
        small = ImageOps.contain(artwork, (55, 55), Image.Resampling.LANCZOS)
        small_canvas = Image.new("RGB", (55, 55), "#0C2532")
        small_canvas.paste(small, ((55 - small.width) // 2,
                                  (55 - small.height) // 2), small)
        small_canvas.save(GENERATED / "setup_small.bmp", format="BMP")
        side = Image.new("RGB", (164, 314), "#0B2431")
        logo = ImageOps.contain(artwork, (156, 156), Image.Resampling.LANCZOS)
        side.paste(logo, ((164 - logo.width) // 2, 64), logo)
        side.save(GENERATED / "setup_sidebar.bmp", format="BMP")

    for target in [FLUTTER_ICON, GENERATED / "twinconnect.ico",
                   GENERATED / "setup_sidebar.bmp",
                   GENERATED / "setup_small.bmp"]:
        if not target.is_file() or target.stat().st_size < 1000:
            raise SystemExit(f"Invalid TwinConnect icon output: {target}")
    print("TwinConnect Windows executable and installer logo generated")


if __name__ == "__main__":
    main()
