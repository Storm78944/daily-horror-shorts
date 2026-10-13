
import os
import re
import subprocess
from pathlib import Path

from groq import Groq
from PIL import Image, ImageDraw, ImageFont

# API-key ophalen
api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    raise RuntimeError("GROQ_API_KEY ontbreekt in GitHub Secrets.")

client = Groq(api_key=api_key)

# Maak een langer horrorverhaal met 12 scènes
print("Een horrorverhaal van ongeveer 1 minuut maken...")

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {
            "role": "system",
            "content": (
                "Write original suspenseful horror stories in English. "
                "Suitable for a general audience, with no graphic violence. "
                "Return exactly 12 short sentences. Each sentence must be "
                "on its own line. Do not number them. Build suspense slowly "
                "and finish with a surprising twist."
            )
        },
        {
            "role": "user",
            "content": (
                "Write a completely new horror story for a one-minute "
                "vertical video. Include an intriguing opening, creepy "
                "events, increasing suspense, and a clever unexpected ending. "
                "Return exactly 12 short sentences, one per line."
            )
        }
    ],
    temperature=1.0,
    max_tokens=700
)

story_text = response.choices[0].message.content or ""
print("Antwoord ontvangen:")
print(story_text)

# Verwerk het verhaal
STORY = [
    line.strip()
    for line in story_text.splitlines()
    if line.strip()
]

# Als het model één alinea terugstuurt, splits die in zinnen
if len(STORY) != 12:
    cleaned = re.sub(r"\s+", " ", story_text).strip()
    STORY = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if sentence.strip()
    ]

# Verwijder eventuele nummering
STORY = [
    re.sub(r"^\s*\d+[\.\)\-:]\s*", "", sentence).strip()
    for sentence in STORY
]
STORY = [sentence for sentence in STORY if sentence]

if len(STORY) != 12:
    raise RuntimeError(
        f"Het verhaal heeft {len(STORY)} zinnen in plaats van 12. "
        "Bekijk de Actions-log."
    )

print("Verhaal klaar:")
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

    # Donkere rode gloed
    draw.ellipse((120, 180, 600, 660), fill=(28, 5, 12))

    # Tekst automatisch over regels verdelen
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

# Maak de video: 12 scènes van 5 seconden = 60 seconden
print("De video van ongeveer 1 minuut renderen...")

subprocess.run([
    "ffmpeg", "-y",
    "-framerate", "1/5",
    "-i", "frames/%03d.png",
    "-vf", "scale=720:1280,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-t", "60",
    str(OUT)
], check=True)

print(f"Video gemaakt: {OUT}")
print("Duur: ongeveer 60 seconden.")
