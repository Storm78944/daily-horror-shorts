
import os
import subprocess
from pathlib import Path

from groq import Groq
from PIL import Image, ImageDraw, ImageFont

# API-key ophalen uit GitHub Secrets
api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    raise RuntimeError(
        "GROQ_API_KEY ontbreekt. Controleer GitHub Secrets."
    )

client = Groq(api_key=api_key)

# Genereer een nieuw horrorverhaal
response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {
            "role": "system",
            "content": (
                "Write original suspenseful horror stories suitable "
                "for a general audience. No graphic violence. "
                "Return exactly six short sentences, one per line. "
                "Do not number them. End with a surprising twist."
            )
        },
        {
            "role": "user",
            "content": (
                "Create a completely new short horror story in English. "
                "Make it suspenseful and end with an unexpected twist. "
                "Return exactly six lines."
            )
        }
    ],
    temperature=1.0,
    max_tokens=300
)

story_text = response.choices[0].message.content.strip()

STORY = [
    line.strip().lstrip("0123456789.-) ").strip('"')
    for line in story_text.splitlines()
    if line.strip()
]

if len(STORY) != 6:
    raise RuntimeError(
        f"Het verhaal heeft {len(STORY)} regels in plaats van 6. "
        "Probeer de workflow opnieuw."
    )

print("Nieuw horrorverhaal:")
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

for i, sentence in enumerate(STORY):
    img = Image.new("RGB", (W, H), (8, 8, 15))
    draw = ImageDraw.Draw(img)

    draw.ellipse((120, 180, 600, 660), fill=(28, 5, 12))

    # Tekst automatisch verdelen over regels
    words = sentence.split()
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

    for text_line in lines:
        bbox = draw.textbbox((0, 0), text_line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2

        draw.text(
            (x, y),
            text_line,
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

# Video maken
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

print(f"Video gemaakt: {OUT}")
