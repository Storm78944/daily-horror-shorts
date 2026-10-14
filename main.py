
import os
import re
import subprocess
import requests
from pathlib import Path
from io import BytesIO

from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps

# --------------------------------------------------
# INSTELLINGEN
# --------------------------------------------------

API_KEY = os.environ.get("GROQ_API_KEY")

if not API_KEY:
    raise RuntimeError("GROQ_API_KEY ontbreekt in GitHub Secrets.")

client = Groq(api_key=API_KEY)

WIDTH, HEIGHT = 720, 1280
SCENES = 12
DURATION = 60
SECONDS_PER_SCENE = DURATION / SCENES

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

# Gratis Unsplash-foto's.
# Controleer de gebruiksvoorwaarden voor publicatie.
PHOTO_IDS = [
    "1519608487953-e999c86e7455",
    "1511497584788-876760111969",
    "1500530855697-b586d89ba3ee",
    "1518837695005-2083093ee35b",
    "1470770841072-f978cf4d019e",
    "1518709268805-4e9042af9f23",
    "1500534623283-312aade485b7",
    "1448375240586-882707db888b",
    "1470252649378-9c29740c9fa8",
    "1519681393784-d120267933ba",
    "1500534314209-a25ddb2bd429",
    "1501785888041-af3ef285b470",
]

# --------------------------------------------------
# 1. VERHAAL MAKEN
# --------------------------------------------------

print("Nieuw horrorverhaal maken...")

response = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    messages=[
        {
            "role": "system",
            "content": (
                "Write original suspenseful horror stories in English. "
                "Suitable for a general audience. No graphic violence. "
                "Create exactly 12 short sentences, one per line. "
                "Aim for around 110 to 130 words in total, suitable for "
                "a one-minute narration. Build suspense and end with "
                "an unexpected twist. No numbering or headings."
            )
        },
        {
            "role": "user",
            "content": (
                "Create a completely new horror story for a vertical "
                "short video. Use vivid scenes, a strong opening, "
                "increasing suspense, and a memorable final twist. "
                "Return exactly 12 sentences."
            )
        }
    ],
    temperature=1.0,
    max_tokens=700
)

story_text = response.choices[0].message.content or ""
story_text = re.sub(r"<think>.*?</think>", "", story_text, flags=re.S)
story_text = re.sub(r"<[^>]+>", "", story_text).strip()

STORY = [
    line.strip()
    for line in story_text.splitlines()
    if line.strip()
]

if len(STORY) != SCENES:
    cleaned = re.sub(r"\s+", " ", story_text)
    STORY = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", cleaned)
        if s.strip()
    ]

STORY = [
    re.sub(r"^\s*\d+[\.\)\-:]\s*", "", s).strip()
    for s in STORY
]

if len(STORY) != SCENES:
    raise RuntimeError(
        f"Het verhaal bevat {len(STORY)} zinnen in plaats van "
        f"{SCENES}. Voer de workflow opnieuw uit."
    )

for sentence in STORY:
    print(sentence)

# --------------------------------------------------
# 2. AI-STEM MAKEN
# --------------------------------------------------

print("Vertelling opnemen met de Engelse AI-stem...")

narration = " ".join(STORY)
tts = gTTS(text=narration, lang="en", slow=False)
tts.save("narration.mp3")

# --------------------------------------------------
# 3. LETTERTYPE LADEN
# --------------------------------------------------

font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
small_font = ImageFont.truetype(font_path, 24)
font = ImageFont.truetype(font_path, 42)

# --------------------------------------------------
# 4. FOTO'S DOWNLOADEN EN SCÈNES MAKEN
# --------------------------------------------------

session = requests.Session()
session.headers.update({"User-Agent": "DarkTalesVideoGenerator/1.0"})

for old_frame in FRAMES.glob("*.png"):
    old_frame.unlink()

for i, (sentence, photo_id) in enumerate(zip(STORY, PHOTO_IDS)):
    print(f"Scène {i + 1}/{SCENES} maken...")

    url = (
        f"https://images.unsplash.com/photo-{photo_id}"
        "?auto=format&fit=crop&w=900&h=1600&q=85"
    )

    try:
        result = session.get(url, timeout=30)
        result.raise_for_status()
        photo = Image.open(BytesIO(result.content)).convert("RGB")
    except Exception as exc:
        raise RuntimeError(
            f"Foto {i + 1} kon niet worden opgehaald: {exc}"
        ) from exc

    photo = ImageOps.fit(photo, (WIDTH, HEIGHT))
    photo = ImageEnhance.Brightness(photo).enhance(0.48)
    photo = ImageEnhance.Color(photo).enhance(0.65)

    # Donker verloop voor leesbare tekst
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(HEIGHT):
        alpha = int(20 + 170 * (y / HEIGHT))
        draw.line((0, y, WIDTH, y), fill=(0, 0, 0, alpha))

    img = photo.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    draw.text(
        (24, 35),
        "DARK TALES",
        font=small_font,
        fill=(255, 55, 65, 255)
    )

    # Tekst automatisch verdelen
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
    y = (HEIGHT - len(lines) * line_height) // 2

    for text_line in lines:
        bbox = draw.textbbox((0, 0), text_line, font=font)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2

        draw.text(
            (x, y),
            text_line,
            font=font,
            fill=(255, 250, 250, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 220)
        )
        y += line_height

    img.convert("RGB").save(FRAMES / f"{i:03d}.png")

# --------------------------------------------------
# 5. VIDEO VAN 60 SECONDEN MAKEN
# --------------------------------------------------

print("Video en vertelling samenvoegen...")

subprocess.run([
    "ffmpeg", "-y",
    "-framerate", "1/5",
    "-i", "frames/%03d.png",
    "-i", "narration.mp3",
    "-vf", "scale=720:1280,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264",
    "-preset", "fast",
    "-c:a", "aac",
    "-b:a", "128k",
    "-af", "apad",
    "-t", str(DURATION),
    "-movflags", "+faststart",
    str(OUT)
], check=True)

print("Klaar! Video opgeslagen als horror-short.mp4")
print("De video duurt ongeveer 60 seconden.")
