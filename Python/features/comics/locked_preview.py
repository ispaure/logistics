"""Small locked placeholder generated without Qt or any decrypted page content."""

from io import BytesIO
from PIL import Image, ImageDraw


def locked_preview(size):
    width, height = (max(16, int(value)) for value in size)
    image = Image.new('RGBA', (width, height), (90, 90, 90, 35))
    draw = ImageDraw.Draw(image)
    unit = max(2, min(width, height) // 10)
    cx, cy = width // 2, height // 2
    draw.arc((cx - 2 * unit, cy - 3 * unit, cx + 2 * unit, cy + unit), 180, 360,
             fill=(120, 120, 120), width=max(1, unit // 2))
    draw.rounded_rectangle((cx - 3 * unit, cy - unit, cx + 3 * unit, cy + 3 * unit),
                           radius=unit, fill=(120, 120, 120))
    draw.ellipse((cx - unit // 2, cy, cx + unit // 2, cy + unit), fill=(230, 230, 230))
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()
