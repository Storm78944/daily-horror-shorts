import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

STORY = [
    "At 3 AM, my phone rang.",
    "It was my sister, who died five years ago.",
    "I answered. She whispered,",
    "\"Don't open the bedroom door.\"",
    "Then I heard my sister's voice behind me:",
    "\"Who are you talking to?\""
]

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

W, H = 720, 1280
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
font = ImageFont.truetype(font_path, 42)

for i, text in enumerate(STORY):
    img = Image.new("RGB", (W, H), (8, 8, 15))
    draw = ImageDraw.Draw(img)

    # Subtle dark red glow
    draw.ellipse((120, 180, 600, 660), fill=(28, 5, 12))

    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] > 620:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)

    line_height = 58
    y = (H - len(lines) * line_height) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill=(245, 235, 235))
        y += line_height

    draw.text((24, 35), "DARK TALES", font=ImageFont.truetype(font_path, 24),
              fill=(180, 40, 50))
    img.save(FRAMES / f"{i:03d}.png")

subprocess.run([
    "ffmpeg", "-y",
    "-framerate", "1/4",
    "-i", "frames/%03d.png",
    "-vf", "scale=720:1280,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264",
    "-t", str(len(STORY) * 4),
    str(OUT)
], check=True)

print(f"Video created: {OUT}")
