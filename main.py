
import os
import subprocess
import random
from pathlib import Path

from groq import Groq
from PIL import Image, ImageDraw, ImageFont

# Controleer of de API-sleutel beschikbaar is
api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    raise RuntimeError(
        "GROQ_API_KEY ontbreekt. Controleer GitHub Secrets."
    )

client = Groq(api_key=api_key)

# Vraag Groq om een nieuw horrorverhaal met zes scènes
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {
            "role": "system",
            "content": (
                "You write original, suspenseful horror stories "
                "suitable for a general audience. No graphic violence. "
                "Return exactly six short lines, one sentence per line. "
                "Do not number the lines. End with a surprising twist."
            )
        },
        {
            "role": "user",
            "content": (
                "Write a completely new short horror story in English. "
                "Use an original idea, build suspense, and finish "
                "with an unexpected twist. Return exactly six lines."
            )
        }
    ],
    temperature=1.0,
    max_tokens=250
)

story_text = response.choices[0].message.content.strip()

STORY = [
    line.strip().lstrip("0123456789.-) ").strip('"')
    for line in story_text.splitlines()
    if line.strip()
]

if len(STORY) != 6:
    raise RuntimeError(
        f"Groq gaf {len(STORY)} regels in plaats van 6. "
        "Probeer de workflow opnieuw."
    )

print("Nieuw verhaal gemaakt door Groq:")
for sentence in STORY:
    print(sentence)

# Video-instellingen
OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

for old_frame in FRAMES.glob("*.png"):
    old_frame.unlink()

W, H = 720, 1280

font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
font = ImageFont.truetype(font_path, 42)
small_font = ImageFont.truetype(font_path, 24)

for i, text in enumerate(STORY):
    img = Image.new("RGB", (W, H), (8, 8, 15))
    draw = ImageDraw.Draw(img)

    # Donkere rode gloed
    draw.ellipse((120, 180, 600, 660), fill=(28, 5, 12))

    # Tekst automatisch over regels verdelen
    words = text.split()
    lines = []
    line = ""

    for word in words:
        test = (line + " " + word).strip()

        if draw.textbbox((0, 0), test, font=font)[2] > 620:
            if line:
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

        draw.text(
            (x, y),
            line,
            font=font,
            fill=(245, 235, 235)
        )
        y += line_height

    draw.text(
        (24, 35),
        "DARK TALES",
        font=small_font,
        fill=(180, 40, 50)
    )

    img.save(FRAMES / f"{i:03d}.png")

# Maak de verticale video
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
