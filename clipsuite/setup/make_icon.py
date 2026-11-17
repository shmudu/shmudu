"""Draw ClipSuite's app icon (1024x1024 PNG): a yellow 9:16 clip frame with a play mark."""

import sys

from PIL import Image, ImageDraw


def draw(path: str, size: int = 1024) -> None:
    s = size / 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40 * s, 40 * s, 984 * s, 984 * s), radius=220 * s, fill=(18, 18, 22, 255))
    # a tall "short" frame with two cut marks
    d.rounded_rectangle((322 * s, 170 * s, 702 * s, 854 * s), radius=60 * s, outline=(255, 229, 0, 255), width=int(44 * s))
    d.polygon([(450 * s, 380 * s), (450 * s, 644 * s), (640 * s, 512 * s)], fill=(255, 229, 0, 255))
    for y in (300, 724):
        d.line((210 * s, y * s, 322 * s, y * s), fill=(255, 229, 0, 255), width=int(30 * s))
        d.line((702 * s, y * s, 814 * s, y * s), fill=(255, 229, 0, 255), width=int(30 * s))
    img.save(path)


if __name__ == "__main__":
    draw(sys.argv[1])
