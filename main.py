
import os
import re
import subprocess
from io import BytesIO
from pathlib import Path

import requests
from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# ==================================================
# DARK TALES - AUTOMATISCHE HORRORVIDEO GENERATOR
# ==================================================

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

W, H = 720, 1280
SCENES = 12
SECONDS_PER_SCENE = 5
MODEL = "openai/gpt-oss-120b"

# Afbeeldingen per soort scène.
# De code kiest een categorie op basis van de verhaaltekst.
IMAGE_OPTIONS = {
    "bedroom": [
        "photo-1505693416388-ac5ce068fe85",
        "photo-1518709268805-4e9042af9f23",
    ],
    "phone": [
        "photo-1512499617640-c74ae3a79d37",
        "photo-1511707171634-5f897ff02aa9",
    ],
    "door": [
        "photo-1518005020951-eccb494ad742",
        "photo-1511497584788-876760111969",
    ],
    "forest": [
        "photo-1448375240586-882707db888b",
        "photo-1511497584788-876760111969",
    ],
    "house": [
        "photo-1518780664697-55e3ad937233",
        "photo-1511818966892-d7d671e672a2",
    ],
    "night": [
        "photo-1470770841072-f978cf4d019e",
        "photo-1519681393784-d120267933ba",
    ],
    "window": [
        "photo-1484154218962-a197022b5858",
        "photo-1518005020951-eccb494ad742",
    ],
    "water": [
        "photo-1500375592092-40eb2168fd21",
        "photo-1518837695005-2083093ee35b",
    ],
    "road": [
        "photo-1519608487953-e999c86e7455",
        "photo-1500530855697-b586d89ba3ee",
    ],
    "hallway": [
        "photo-1511818966892-d7d671e672a2",
        "photo-1518005020951-eccb494ad742",
    ],
    "shadow": [
        "photo-1518709268805-4e9042af9f23",
        "photo-1511497584788-876760111969",
    ],
    "grave": [
        "photo-1500534623283-312aade485b7",
        "photo-1448375240586-882707db888b",
    ],
    "mirror": [
        "photo-1518005020951-eccb494ad742",
        "photo-1505693416388-ac5ce068fe85",
    ],
    "generic": [
        "photo-1518709268805-4e9042af9f23",
        "photo-1448375240586-882707db888b",
        "photo-1470770841072-f978cf4d019e",
        "photo-1511497584788-876760111969",
    ],
}

# Reserveverhaal als Groq niet beschikbaar is.
FALLBACK_STORY = [
    "At midnight, I heard footsteps upstairs.",
    "I live alone, and every door was locked.",
    "My phone suddenly lit up on the table.",
    "An unknown number sent me a message.",
    "It said, do not look at the staircase.",
    "Then I heard a quiet voice behind me.",
    "The voice sounded exactly like my own.",
    "I slowly turned toward the dark hallway.",
    "A shadow stood beside my bedroom door.",
    "My phone rang, showing my own number.",
    "I answered and heard myself whispering.",
    "Stop looking at the hallway. It is behind you.",
]

# ==================================================
# 1. VERHAAL MAKEN
# ==================================================

def split_story(text):
    if not text:
        return []

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text).strip()

    # Verwijder een eventueel titelblok.
    text = re.sub(
        r"(?im)^\s*(story|horror story|title|verhaal)\s*:.*$",
        "",
        text,
    )

    # Probeer eerst één zin per regel.
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[\.\)\-:]|[-*•])\s*", "", line)
        line = line.strip()
        if line:
            lines.append(line)

    # Als de AI een alinea terugstuurt, splits op leestekens.
    if len(lines) < SCENES:
        cleaned = re.sub(r"\s+", " ", text).strip()
        lines = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
            if sentence.strip()
        ]

    # Verwijder nummering en lege regels.
    result = []
    for line in lines:
        line = re.sub(r"^\s*\d+[\.\)\-:]\s*", "", line).strip()
        if line:
            result.append(line)

    return result


def generate_story():
    print("Nieuw horrorverhaal maken...")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY ontbreekt. Controleer GitHub Secrets."
        )

    client = Groq(api_key=api_key)

    prompt = """
Write an original horror story in English for a YouTube Short.

Return exactly 12 sentences.
Put each sentence on a separate line.
Number the sentences from 1 to 12.
Every sentence should describe one clear moment or scene.
Include specific visual details that could be shown in a photograph.
Build suspense and end with a surprising twist.
Use natural, simple English.
Do not add a title or any explanation.
Keep the story suitable for a general audience.
"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a horror storyteller. "
                            "Return exactly 12 numbered sentences."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_completion_tokens=1200,
            )

            story_text = response.choices[0].message.content or ""
            story = split_story(story_text)

            if len(story) >= SCENES:
                print("Nieuw AI-verhaal ontvangen.")
                return story[:SCENES]

            print(
                f"Poging {attempt + 1}: "
                f"{len(story)} zinnen ontvangen."
            )

        except Exception as exc:
            print(f"AI-poging {attempt + 1} mislukt: {exc}")

    print("Reserveverhaal gebruiken.")
    return FALLBACK_STORY.copy()


# ==================================================
# 2. PASSENDE AFBEELDING KIEZEN
# ==================================================

def choose_image_category(sentence):
    """
    Kies een afbeeldingscategorie op basis van woorden
    in de huidige scène.
    """
    text = sentence.lower()

    categories = [
        ("bedroom", [
            "bedroom", "bed", "pillow", "mattress", "sleeping",
        ]),
        ("phone", [
            "phone", "call", "message", "text", "number",
            "ringing", "screen", "notification",
        ]),
        ("door", [
            "door", "locked", "knock", "handle", "opened",
        ]),
        ("forest", [
            "forest", "woods", "trees", "branches", "leaves",
        ]),
        ("house", [
            "house", "home", "building", "attic", "basement",
        ]),
        ("hallway", [
            "hallway", "corridor", "stairs", "staircase",
            "upstairs", "downstairs", "landing",
        ]),
        ("window", [
            "window", "curtain", "glass", "outside",
        ]),
        ("water", [
            "water", "ocean", "lake", "river", "drowning",
        ]),
        ("road", [
            "road", "street", "car", "driving", "highway",
        ]),
        ("grave", [
            "grave", "cemetery", "tombstone", "buried",
            "funeral", "graveyard",
        ]),
        ("mirror", [
            "mirror", "reflection", "reflected",
        ]),
        ("shadow", [
            "shadow", "silhouette", "figure", "shape",
            "standing behind", "dark figure",
        ]),
        ("night", [
            "midnight", "night", "darkness", "moon",
            "stars", "3 am", "3 a.m.",
        ]),
    ]

    # De eerste passende categorie wordt gebruikt.
    for category, keywords in categories:
        if any(word in text for word in keywords):
            return category

    return "generic"


def download_background(sentence, index):
    category = choose_image_category(sentence)
    photo_ids = IMAGE_OPTIONS[category]

    # Andere afbeeldingen uit dezelfde categorie per scène.
    photo_id = photo_ids[index % len(photo_ids)]

    url = (
        f"https://images.unsplash.com/{photo_id}"
        "?auto=format&fit=crop&w=720&h=1280&q=85"
    )

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "DarkTalesVideoGenerator/1.0"},
        )
        response.raise_for_status()

        image = Image.open(BytesIO(response.content)).convert("RGB")
        image = image.resize((W, H))
        image = ImageEnhance.Brightness(image).enhance(0.42)

        print(f"Scène {index + 1}: categorie '{category}'")
        return image

    except Exception as exc:
        print(f"Afbeelding niet beschikbaar: {exc}")

        # Eigen achtergrond als de download mislukt.
        image = Image.new("RGB", (W, H), (8, 8, 15))
        draw = ImageDraw.Draw(image)
        draw.ellipse(
            (80, 180, 640, 900),
            fill=(28, 5, 12),
        )
        return image


# ==================================================
# 3. TEKST EN ACHTERGRONDEN COMBINEREN
# ==================================================

def load_font(size):
    font_path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    )
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


def create_scene(sentence, index):
    image = download_background(sentence, index).convert("RGBA")

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 65))
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    font = load_font(42)
    small_font = load_font(24)

    # Tekst afbreken zodat deze binnen het scherm blijft.
    words = sentence.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        width = draw.textbbox((0, 0), test_line, font=font)[2]

        if width > W - 100 and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test_line

    if current_line:
        lines.append(current_line)

    line_height = 58
    total_height = len(lines) * line_height
    y = (H - total_height) // 2
    padding = 28

    draw.rounded_rectangle(
        (
            35,
            y - padding,
            W - 35,
            y + total_height + padding,
        ),
        radius=22,
        fill=(0, 0, 0, 180),
    )

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (W - text_width) // 2

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

    draw.text(
        (30, 35),
        "DARK TALES",
        font=small_font,
        fill=(220, 190, 190, 230),
    )

    frame_path = FRAMES / f"frame_{index + 1:02d}.png"
    image.convert("RGB").save(frame_path)


# ==================================================
# 4. VIDEO EN ENGELSE STEM MAKEN
# ==================================================

def main():
    story = generate_story()

    print("\nVerhaal voor de video:")
    for i, sentence in enumerate(story, start=1):
        print(f"{i}. {sentence}")

    print("\nEngelse vertelling maken...")
    narration = " ".join(story)
    gTTS(text=narration, lang="en", slow=False).save("narration.mp3")

    for old_frame in FRAMES.glob("frame_*.png"):
        old_frame.unlink()

    print("\nScènes maken...")
    for i, sentence in enumerate(story):
        create_scene(sentence, i)

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
    print(f"Grootte: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
