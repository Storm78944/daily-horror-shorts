
import os
import re
import subprocess
from pathlib import Path
from textwrap import wrap

import requests
from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# --------------------------------------------------
# INSTELLINGEN
# --------------------------------------------------

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

W, H = 720, 1280
SCENES = 12
SECONDS_PER_SCENE = 5
MODEL = "openai/gpt-oss-120b"

# Gratis Unsplash-foto's. Als een foto niet beschikbaar is,
# maakt het programma zelf een donkere achtergrond.
PHOTO_IDS = [
    "photo-1518709268805-4e9042af9f23",
    "photo-1511497584788-876760111969",
    "photo-1500530855697-b586d89ba3ee",
    "photo-1470770841072-f978cf4d019e",
    "photo-1518837695005-2083093ee35b",
    "photo-1500534623283-312aade485b7",
    "photo-1448375240586-882707db888b",
    "photo-1470252649378-9c29740c9fa8",
    "photo-1501785888041-af3ef285b470",
    "photo-1519681393784-d120267933ba",
    "photo-1472214103451-9374bd1c798e",
    "photo-1500534314209-a25ddb2bd429",
]

# Reserveverhaal voor als de AI geen bruikbaar verhaal terugstuurt.
# De video kan dan alsnog worden gemaakt.
FALLBACK_STORY = [
    "At midnight, I heard someone walking upstairs.",
    "I live alone, and my front door was locked.",
    "I checked my phone, but there was no signal.",
    "Then a message appeared from an unknown number.",
    "It said, whatever you do, stay downstairs.",
    "A second message arrived a moment later.",
    "It said, I can see you from the hallway.",
    "I slowly turned toward the dark staircase.",
    "A shadow moved across the wall above me.",
    "Then my phone rang with my own number.",
    "I answered, and heard my voice whispering.",
    "Stop looking at the stairs. It is behind you.",
]

# --------------------------------------------------
# 1. NIEUW HORRORVERHAAL MAKEN
# --------------------------------------------------

def split_story(text):
    """Zet AI-tekst om naar losse zinnen."""
    if not text:
        return []

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r", "\n").strip()

    sentences = []

    # Eerst proberen: één zin per regel.
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Verwijder nummering, opsommingstekens en aanhalingstekens.
        line = re.sub(r"^\s*(?:\d+[\.\)\-:]|[-*•])\s*", "", line)
        line = re.sub(
            r"^(?:story|horror story|here is the story)\s*:\s*",
            "",
            line,
            flags=re.I,
        )
        line = line.strip()

        if line:
            sentences.append(line)

    # Als de AI alles in één alinea heeft gezet, splits op leestekens.
    if len(sentences) < SCENES:
        cleaned = re.sub(r"\s+", " ", text).strip()
        sentences = [
            s.strip(" \t-*•0123456789")
            for s in re.split(r"(?<=[.!?])\s+", cleaned)
            if s.strip(" \t-*•0123456789")
        ]

    # Verwijder eventuele lege regels en kopjes.
    sentences = [
        s for s in sentences
        if s and s.lower() not in {
            "story", "horror story", "here is the story"
        }
    ]

    return sentences


def generate_story():
    print("Nieuw horrorverhaal maken...")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY ontbreekt. Controleer GitHub Secrets."
        )

    client = Groq(api_key=api_key)

    prompt = """
Write an original, suspenseful horror story in English for a YouTube Short.

Requirements:
- Exactly 12 sentences.
- Put each sentence on its own line.
- Number the lines from 1 to 12.
- Use simple, natural English.
- Make the story suspenseful, with a strong twist at the end.
- Make it suitable for a general audience.
- Do not include a title, introduction, explanation, or extra text.
"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You write original short horror stories. "
                            "Follow the requested format exactly."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_completion_tokens=1200,
            )

            message = response.choices[0].message
            story_text = message.content or ""
            story = split_story(story_text)

            if len(story) >= SCENES:
                story = story[:SCENES]
                print("Nieuw AI-verhaal ontvangen.")
                return story

            print(
                f"AI-poging {attempt + 1}: "
                f"{len(story)} bruikbare zinnen ontvangen."
            )

        except Exception as exc:
            print(f"AI-poging {attempt + 1} mislukt: {exc}")

    print("Geen bruikbaar AI-verhaal ontvangen.")
    print("Het reserveverhaal wordt gebruikt.")
    return FALLBACK_STORY.copy()


STORY = generate_story()

print("\nVerhaal voor de video:")
for i, sentence in enumerate(STORY, start=1):
    print(f"{i}. {sentence}")

# --------------------------------------------------
# 2. ENGELSE AI-STEM MAKEN
# --------------------------------------------------

print("\nVertelling maken...")

narration = " ".join(STORY)
tts = gTTS(text=narration, lang="en", slow=False)
tts.save("narration.mp3")

# --------------------------------------------------
# 3. LETTERTYPES LADEN
# --------------------------------------------------

font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

try:
    font = ImageFont.truetype(font_path, 42)
    small_font = ImageFont.truetype(font_path, 24)
except OSError:
    font = ImageFont.load_default()
    small_font = ImageFont.load_default()

# --------------------------------------------------
# 4. ACHTERGRONDEN DOWNLOADEN
# --------------------------------------------------

session = requests.Session()
session.headers.update(
    {"User-Agent": "DarkTalesVideoGenerator/1.0"}
)

for old_frame in FRAMES.glob("*.png"):
    old_frame.unlink()


def make_background(photo_id, index):
    """Download een achtergrond of maak zelf een donkere afbeelding."""
    url = (
        f"https://images.unsplash.com/{photo_id}"
        "?auto=format&fit=crop&w=720&h=1280&q=80"
    )

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()

        from io import BytesIO
        image = Image.open(BytesIO(response.content)).convert("RGB")
        image = image.resize((W, H))
        image = ImageEnhance.Brightness(image).enhance(0.42)
        return image

    except Exception as exc:
        print(f"Foto {index + 1} niet beschikbaar: {exc}")
        print("Donkere reserveachtergrond gebruiken.")

        image = Image.new("RGB", (W, H), (8, 8, 15))
        draw = ImageDraw.Draw(image)
        draw.ellipse(
            (80, 180, 640, 900),
            fill=(28, 5, 12),
        )
        return image


# --------------------------------------------------
# 5. SCÈNES MET TEKST MAKEN
# --------------------------------------------------

for i, sentence in enumerate(STORY):
    print(f"Scène {i + 1}/{SCENES} maken...")

    image = make_background(PHOTO_IDS[i], i)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 65))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(image)

    # Tekst automatisch over meerdere regels verdelen.
    words = sentence.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()

        if draw.textbbox((0, 0), test_line, font=font)[2] > W - 100:
            if current_line:
                lines.append(current_line)
            current_line = word
        else:
            current_line = test_line

    if current_line:
        lines.append(current_line)

    line_height = 62
    total_height = len(lines) * line_height
    y = (H - total_height) // 2

    # Donkere tekstachtergrond voor betere leesbaarheid.
    padding = 28
    box_top = y - padding
    box_bottom = y + total_height + padding

    draw.rounded_rectangle(
        (35, box_top, W - 35, box_bottom),
        radius=22,
        fill=(0, 0, 0, 175),
    )

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (W - text_width) // 2

        # Schaduw en witte tekst.
        draw.text(
            (x + 2, y + 3),
            line,
            font=font,
            fill=(0, 0, 0, 255),
        )
        draw.text(
            (x, y),
            line,
            font=font,
            fill=(255, 255, 255, 255),
        )
        y += line_height

    # Kleine kanaalnaam.
    draw.text(
        (30, 35),
        "DARK TALES",
        font=small_font,
        fill=(220, 190, 190, 230),
    )

    frame_path = FRAMES / f"frame_{i + 1:02d}.png"
    image.convert("RGB").save(frame_path, quality=95)

# --------------------------------------------------
# 6. VIDEO MAKEN MET FFMPEG
# --------------------------------------------------

print("\nVideo van ongeveer 60 seconden maken...")

command = [
    "ffmpeg",
    "-y",
    "-hide_banner",
    "-loglevel", "error",
    "-framerate", f"1/{SECONDS_PER_SCENE}",
    "-i", str(FRAMES / "frame_%02d.png"),
    "-i", "narration.mp3",
    "-map", "0:v:0",
    "-map", "1:a:0",
    "-vf", "fps=30,format=yuv420p",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "23",
    "-af", "apad",
    "-t", str(SCENES * SECONDS_PER_SCENE),
    "-c:a", "aac",
    "-b:a", "128k",
    "-movflags", "+faststart",
    str(OUT),
]

subprocess.run(command, check=True)

if not OUT.exists() or OUT.stat().st_size == 0:
    raise RuntimeError("De video is niet goed aangemaakt.")

print(f"\nKlaar! Video gemaakt: {OUT}")
print(f"Bestandsgrootte: {OUT.stat().st_size // 1024} KB")
