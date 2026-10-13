
import os
import re
import subprocess
from pathlib import Path

from groq import Groq
from PIL import Image, ImageDraw, ImageFont

api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    raise RuntimeError("GROQ_API_KEY ontbreekt in GitHub Secrets.")

client = Groq(api_key=api_key)

print("Een nieuw horrorverhaal maken...")

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {
            "role": "system",
            "content": (
                "Write an original suspenseful horror story in English. "
                "Suitable for a general audience, with no graphic violence. "
                "Return exactly six short sentences. Put each sentence "
                "on its own line. Do not number the sentences."
            )
        },
        {
            "role": "user",
            "content": (
                "Write a new horror story with a creepy atmosphere "
                "and an unexpected twist at the end. Exactly six sentences."
            )
        }
    ],
    temperature=1.0,
    max_tokens=400
)

story_text = response.choices[0].message.content or ""

print("Antwoord ontvangen:")
print(repr(story_text))

# Eerst proberen de regels rechtstreeks te gebruiken
STORY = [
    line.strip()
    for line in story_text.splitlines()
    if line.strip()
]

# Als het verhaal als één alinea terugkomt, splits het in zinnen
if len(STORY) != 6:
    cleaned = re.sub(r"\s+", " ", story_text).strip()
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    STORY = [s.strip() for s in sentences if s.strip()]

# Verwijder eventuele nummering
STORY = [
    re.sub(r"^\s*\d+[\.\)\-:]\s*", "", sentence).strip()
    for sentence in STORY
]
STORY = [sentence for sentence in STORY if sentence]

if len(STORY) != 6:
    raise RuntimeError(
        f"Het model gaf {len(STORY)} zinnen in plaats van 6. "
        "Bekijk 'Antwoord ontvangen' in de Actions-log."
    )

print("Verhaal:")
for sentence in STORY:
    print(sentence)

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

print("Video renderen...")

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
