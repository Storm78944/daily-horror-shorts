
import os
import re
import subprocess
from io import BytesIO
from pathlib import Path
from html import unescape

import requests
from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# ==================================================
# DARK TALES
# ==================================================

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

W, H = 720, 1280
SCENES = 12
SECONDS_PER_SCENE = 5
MODEL = "openai/gpt-oss-120b"

session = requests.Session()
session.headers.update({
    "User-Agent": "DarkTalesEducationalProject/1.0"
})

FALLBACK_STORY = [
    "At midnight, a phone lit up on a wooden table.",
    "A bedroom door slowly opened into a dark hallway.",
    "A shadow appeared behind the frosted window.",
    "Someone left muddy footprints across the floor.",
    "An old photograph showed a strange face.",
    "The lights went out in the empty house.",
    "A message appeared on the phone screen.",
    "The message showed a picture of the staircase.",
    "A tall silhouette stood at the top of the stairs.",
    "The bedroom mirror reflected an empty room.",
    "Three slow knocks came from inside the closet.",
    "The phone rang again, and the caller was me.",
]

# ==================================================
# 1. VERHAAL GENEREREN
# ==================================================

def split_story(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", "", text).strip()

    result = []

    for line in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[\.\)\-:]|[-*•])\s*", "", line)
        line = line.strip()
        if line:
            result.append(line)

    if len(result) < SCENES:
        cleaned = re.sub(r"\s+", " ", text).strip()
        result = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", cleaned)
            if s.strip()
        ]

    return result


def generate_story():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY ontbreekt in GitHub Secrets.")

    client = Groq(api_key=key)

    prompt = """
Write an original horror story in English for a YouTube Short.
Return exactly 12 numbered sentences, one per line.
Each sentence must describe one concrete, visible scene.
Mention specific objects and locations that can be illustrated.
Keep the scenes in the same story and end with a twist.
No title or explanations. Suitable for a general audience.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Write clear, visual horror stories.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_completion_tokens=1400,
        )

        story = split_story(response.choices[0].message.content or "")
        if len(story) >= SCENES:
            return story[:SCENES]

        print("AI gaf te weinig zinnen; reserveverhaal gebruiken.")

    except Exception as exc:
        print(f"AI-verhaal niet beschikbaar: {exc}")

    return FALLBACK_STORY.copy()


# ==================================================
# 2. AFBEELDINGSTHEMA BEPALEN
# ==================================================

THEMES = [
    ("phone", ["phone", "mobile", "caller", "call", "message", "screen"]),
    ("door", ["door", "doorway", "knock", "handle", "closet"]),
    ("hallway", ["hallway", "corridor", "stairs", "staircase", "footsteps"]),
    ("window", ["window", "curtain", "glass"]),
    ("bedroom", ["bedroom", "bed", "pillow", "sleep"]),
    ("mirror", ["mirror", "reflection", "reflected"]),
    ("photo", ["photograph", "picture", "portrait", "photo"]),
    ("footprints", ["footprints", "footsteps", "muddy tracks"]),
    ("house", ["house", "home", "building", "attic", "basement"]),
    ("shadow", ["shadow", "silhouette", "figure", "stranger", "face"]),
    ("light", ["lights", "dark", "darkness", "midnight", "lamp"]),
]


def choose_theme(sentence):
    words = set(re.findall(r"[a-z]+", sentence.lower()))

    for theme, keywords in THEMES:
        if words.intersection(keywords):
            return theme

    return "shadow"


# ==================================================
# 3. PASSENDE FOTO ZOEKEN
# ==================================================

def search_photo(sentence, theme):
    # Zoek met het voorwerp uit de zin en een fotografieterm.
    queries = [
        f"{theme} {sentence} photograph",
        f"{theme} dark room photograph",
    ]

    for query in queries:
        try:
            response = session.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrnamespace": 6,
                    "gsrlimit": 8,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 900,
                    "format": "json",
                },
                timeout=20,
            )
            response.raise_for_status()

            pages = response.json().get("query", {}).get("pages", {})
            candidates = list(pages.values())

            # Alleen een resultaat gebruiken als de bestandsnaam
            # duidelijk bij het onderwerp past.
            for page in candidates:
                title = page.get("title", "").lower()
                title_words = set(re.findall(r"[a-z]+", title))

                if theme not in title_words and not (
                    theme == "phone" and
                    title_words.intersection({"mobile", "telephone"})
                ):
                    continue

                info = page.get("imageinfo", [{}])[0]
                metadata = info.get("extmetadata", {})
                license_name = unescape(
                    metadata.get("LicenseShortName", {}).get("value", "")
                )

                url = info.get("thumburl") or info.get("url")
                if not url or not license_name:
                    continue

                image_response = session.get(url, timeout=20)
                image_response.raise_for_status()

                image = Image.open(
                    BytesIO(image_response.content)
                ).convert("RGB")

                # Alleen echte afbeeldingsbestanden gebruiken.
                if image.width < 250 or image.height < 250:
                    continue

                return image, (
                    f"{page.get('title', '')} | "
                    f"License: {license_name} | "
                    f"{info.get('descriptionurl', '')}"
                )

        except Exception as exc:
            print(f"Zoeken mislukt voor '{query}': {exc}")

    return None, None


# ==================================================
# 4. RESERVESCÈNES MAKEN
# ==================================================

def load_font(size):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def draw_object_scene(sentence, theme):
    """
    Maak een eenvoudige, donkere illustratie in plaats van
    een willekeurige foto wanneer geen passende foto gevonden is.
    """
    image = Image.new("RGB", (W, H), (8, 8, 16))
    draw = ImageDraw.Draw(image)

    # Subtiele donkere achtergrond en vloer.
    draw.rectangle((0, 850, W, H), fill=(18, 15, 25))
    draw.ellipse((100, 150, 620, 900), fill=(22, 8, 17))

    if theme == "phone":
        draw.rounded_rectangle(
            (250, 420, 470, 800),
            radius=28,
            fill=(45, 45, 55),
            outline=(180, 180, 190),
            width=5,
        )
        draw.rounded_rectangle(
            (270, 460, 450, 730),
            radius=12,
            fill=(70, 90, 115),
        )
        draw.ellipse((330, 500, 390, 560), fill=(220, 220, 240))

    elif theme in ("door", "hallway", "house", "bedroom"):
        draw.rectangle(
            (180, 250, 540, 1000),
            fill=(30, 22, 27),
            outline=(120, 90, 80),
            width=8,
        )
        if theme in ("door", "hallway"):
            draw.polygon(
                [(190, 260), (470, 320), (470, 990), (190, 990)],
                fill=(10, 9, 15),
            )
            draw.ellipse((420, 600, 440, 620), fill=(180, 140, 80))
        else:
            draw.rectangle((240, 680, 490, 870), fill=(50, 35, 42))
            draw.rectangle((250, 620, 480, 700), fill=(90, 70, 80))

    elif theme == "window":
        draw.rectangle(
            (160, 250, 560, 800),
            fill=(12, 15, 28),
            outline=(150, 145, 155),
            width=8,
        )
        draw.line((360, 250, 360, 800), fill=(120, 120, 140), width=6)
        draw.line((160, 525, 560, 525), fill=(120, 120, 140), width=6)

    elif theme == "mirror":
        draw.rounded_rectangle(
            (180, 240, 540, 850),
            radius=100,
            fill=(45, 48, 60),
            outline=(150, 130, 115),
            width=12,
        )
        draw.ellipse((290, 350, 430, 520), fill=(15, 15, 24))
        draw.polygon(
            [(260, 760), (300, 540), (420, 540), (460, 760)],
            fill=(18, 18, 28),
        )

    elif theme == "photo":
        draw.rectangle(
            (170, 300, 550, 820),
            fill=(75, 60, 50),
            outline=(180, 155, 110),
            width=15,
        )
        draw.rectangle((200, 330, 520, 790), fill=(22, 24, 34))
        draw.ellipse((290, 410, 430, 550), fill=(45, 40, 50))
        draw.polygon(
            [(250, 750), (290, 550), (430, 550), (470, 750)],
            fill=(40, 35, 45),
        )

    elif theme == "footprints":
        for x, y in [
            (270, 400), (390, 500), (270, 600),
            (390, 700), (270, 800),
        ]:
            draw.ellipse((x, y, x + 45, y + 80), fill=(55, 35, 35))

    else:
        # Een silhouet als veilige reserve voor andere onderwerpen.
        draw.ellipse((270, 350, 450, 530), fill=(3, 3, 8))
        draw.polygon(
            [(240, 1000), (270, 520), (450, 520), (500, 1000)],
            fill=(3, 3, 8),
        )

    return image


# ==================================================
# 5. TEKST OVER DE SCÈNE ZETTEN
# ==================================================

def create_scene(sentence, index, credits):
    theme = choose_theme(sentence)
    image, credit = search_photo(sentence, theme)

    if image is None:
        print(f"Geen passende foto; illustratie voor '{theme}' maken.")
        image = draw_object_scene(sentence, theme)
        credits.append(
            f"Scène {index + 1}: zelfgemaakte illustratie ({theme})"
        )
    else:
        image = image.convert("RGB")
        image.thumbnail((W, H))

        canvas = Image.new("RGB", (W, H), (8, 8, 16))
        canvas.paste(
            image,
            ((W - image.width) // 2, (H - image.height) // 2),
        )
        image = ImageEnhance.Brightness(canvas).enhance(0.42)
        credits.append(f"Scène {index + 1}: {credit}")

    image = image.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 65))
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    font = load_font(40)
    small_font = load_font(24)

    lines = []
    current = ""

    for word in sentence.split():
        candidate = f"{current} {word}".strip()

        if draw.textbbox((0, 0), candidate, font=font)[2] > W - 100:
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)

    line_height = 56
    total_height = len(lines) * line_height
    y = (H - total_height) // 2

    draw.rounded_rectangle(
        (35, y - 25, W - 35, y + total_height + 25),
        radius=20,
        fill=(0, 0, 0, 190),
    )

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2

        draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height

    draw.text(
        (30, 35),
        "DARK TALES",
        font=small_font,
        fill=(230, 200, 200),
    )

    image.convert("RGB").save(FRAMES / f"frame_{index + 1:02d}.png")


# ==================================================
# 6. VIDEO MAKEN
# ==================================================

def main():
    story = generate_story()

    print("\nVerhaal:")
    for i, sentence in enumerate(story, start=1):
        print(f"{i}. {sentence}")

    print("\nEngelse vertelling maken...")
    gTTS(text=" ".join(story), lang="en", slow=False).save(
        "narration.mp3"
    )

    for old_frame in FRAMES.glob("frame_*.png"):
        old_frame.unlink()

    credits = []

    for i, sentence in enumerate(story):
        print(f"\nScène {i + 1}/{SCENES}")
        create_scene(sentence, i, credits)

    Path("image-credits.txt").write_text(
        "\n\n".join(credits),
        encoding="utf-8",
    )

    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", f"1/{SECONDS_PER_SCENE}",
        "-i", str(FRAMES / "frame_%02d.png"),
        "-i", "narration.mp3",
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-af", "apad", "-t", str(SCENES * SECONDS_PER_SCENE),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(OUT),
    ]

    subprocess.run(command, check=True)

    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("De video is niet goed aangemaakt.")

    print(f"\nVideo klaar: {OUT}")
    print("Bron- en licentiegegevens staan in image-credits.txt")


if __name__ == "__main__":
    main()
