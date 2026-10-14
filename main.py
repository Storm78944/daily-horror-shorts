
import os
import re
import random
import subprocess
from io import BytesIO
from pathlib import Path
from html import unescape

import requests
from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

W, H = 720, 1280
SCENES = 12
SECONDS_PER_SCENE = 5
MODEL = "openai/gpt-oss-120b"

session = requests.Session()
session.headers.update({
    "User-Agent": "DarkTalesEducationalProject/2.0 (video project)"
})

# Houd bij welke afbeeldingen al gebruikt zijn in deze video.
USED_IMAGES = set()

FALLBACK_STORY = [
    "At midnight, a phone glowed on a wooden table.",
    "The bedroom door opened into a dark hallway.",
    "A strange silhouette appeared behind the window.",
    "Muddy footprints crossed the empty floor.",
    "An old photograph showed a face nobody recognized.",
    "The lights went out inside the abandoned house.",
    "A new message appeared on the phone screen.",
    "The message showed a photograph of the staircase.",
    "A tall figure waited at the top of the stairs.",
    "The bedroom mirror reflected an empty room.",
    "Three knocks came from inside the wooden closet.",
    "The phone rang again, and the caller was me."
]

# ==================================================
# 1. VERHAAL GENEREREN
# ==================================================

def split_story(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", "", text).strip()

    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[\.\)\-:]|[-*•])\s*", "", line)
        if line.strip():
            lines.append(line.strip())

    if len(lines) < SCENES:
        text = " ".join(lines)
        lines = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", text)
            if s.strip()
        ]

    return lines


def generate_story():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY ontbreekt in GitHub Secrets.")

    try:
        client = Groq(api_key=key)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Write original horror stories with concrete visual scenes."
                },
                {
                    "role": "user",
                    "content": (
                        "Write an original English horror story for a YouTube Short. "
                        "Return exactly 12 numbered sentences, one per line. "
                        "Every sentence must describe a different, specific, visible scene. "
                        "Use concrete objects, places and actions. "
                        "Avoid repeating the same setting in consecutive scenes. "
                        "End with a twist. No title or explanations. "
                        "Suitable for a general audience."
                    )
                }
            ],
            temperature=0.9,
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
# 2. SCÈNE HERKENNEN EN ZOEKTERMEN MAKEN
# ==================================================

SCENE_TYPES = [
    ("phone", ["phone", "mobile", "telephone", "caller", "calling", "message", "screen"]),
    ("footprints", ["footprints", "footprint", "muddy tracks", "muddy shoes"]),
    ("stairs", ["staircase", "stairs", "steps", "landing"]),
    ("mirror", ["mirror", "reflection", "reflected"]),
    ("photograph", ["photograph", "photographs", "portrait", "old photo", "picture"]),
    ("window", ["window", "curtain", "glass pane"]),
    ("closet", ["closet", "wardrobe", "cupboard"]),
    ("door", ["door", "doorway", "door handle", "knocking", "knocks"]),
    ("hallway", ["hallway", "corridor", "passage"]),
    ("bedroom", ["bedroom", "bed", "pillow"]),
    ("house", ["abandoned house", "haunted house", "empty house", "old house", "building"]),
    ("shadow", ["shadow", "silhouette", "stranger", "figure", "unknown person"]),
    ("light", ["light", "lights", "lamp", "darkness", "midnight"]),
]

SCENE_SEARCH_TERMS = {
    "phone": ["smartphone on table", "telephone in dark room", "phone glowing at night"],
    "footprints": ["muddy footprints on floor", "muddy footprints in hallway", "shoe prints on dusty floor"],
    "stairs": ["dark staircase inside old house", "wooden stairs abandoned building", "staircase in dim light"],
    "mirror": ["old mirror in dark bedroom", "mirror reflection empty room", "antique mirror dark room"],
    "photograph": ["old framed photograph", "vintage portrait photograph", "old family photo frame"],
    "window": ["dark window at night", "window in abandoned house", "silhouette behind window"],
    "closet": ["open wooden closet dark room", "old wardrobe in bedroom", "dark closet doorway"],
    "door": ["open door dark hallway", "old wooden door dim light", "doorway in abandoned house"],
    "hallway": ["long dark hallway", "corridor abandoned building", "empty corridor at night"],
    "bedroom": ["dark abandoned bedroom", "bed in dim bedroom", "old bedroom at night"],
    "house": ["abandoned house at night", "old house exterior dark", "haunted house in fog"],
    "shadow": ["human silhouette in dark hallway", "shadowy figure in doorway", "mysterious silhouette at night"],
    "light": ["single lamp in dark room", "dim light abandoned room", "dark room with light"],
    "unknown": ["abandoned interior at night", "dark room atmospheric photograph", "old building interior"],
}

STOPWORDS = {
    "the", "and", "with", "from", "into", "onto", "then", "there",
    "that", "this", "was", "were", "had", "has", "have", "for",
    "while", "when", "where", "someone", "something", "appeared",
    "slowly", "suddenly", "again", "inside", "outside", "showed",
    "started", "began", "looked", "could", "would", "their", "his",
    "her", "its", "they", "him", "she", "after", "before", "under",
    "over", "near", "one", "two", "three", "old", "dark", "empty"
}


def choose_theme(sentence):
    text = sentence.lower()

    # Eerst de specifiekere onderwerpen controleren.
    for theme in [
        "footprints", "photograph", "phone", "stairs", "mirror",
        "closet", "window", "door", "hallway", "bedroom", "house",
        "shadow", "light"
    ]:
        for candidate, keywords in SCENE_TYPES:
            if candidate == theme and any(k in text for k in keywords):
                return theme

    return "unknown"


def make_queries(sentence, theme):
    queries = []

    # Zoek eerst naar een concrete scène die bij de zin past.
    for term in SCENE_SEARCH_TERMS.get(theme, SCENE_SEARCH_TERMS["unknown"]):
        queries.append(term)

    # Gebruik ook belangrijke woorden uit de zin zelf.
    words = re.findall(r"[a-z]+", sentence.lower())
    important = [
        word for word in words
        if len(word) >= 4 and word not in STOPWORDS
    ]

    if important:
        queries.append(" ".join(important[:5]) + " photograph")
        queries.append(" ".join(important[:3]) + " interior")

    # Verwijder dubbele zoekopdrachten.
    return list(dict.fromkeys(queries))


# ==================================================
# 3. FOTO'S ZOEKEN EN DUBBELS VERMIJDEN
# ==================================================

def search_photo(sentence, theme):
    queries = make_queries(sentence, theme)

    for query in queries:
        try:
            response = session.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrnamespace": 6,
                    "gsrlimit": 15,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 900,
                    "format": "json",
                },
                timeout=25,
            )
            response.raise_for_status()

            pages = response.json().get("query", {}).get("pages", {})
            candidates = list(pages.values())
            random.shuffle(candidates)

            scored = []

            query_words = set(re.findall(r"[a-z]+", query.lower()))
            query_words -= STOPWORDS

            for page in candidates:
                title = page.get("title", "")
                title_words = set(re.findall(r"[a-z]+", title.lower()))

                info = page.get("imageinfo", [{}])[0]
                metadata = info.get("extmetadata", {})

                license_name = unescape(
                    metadata.get("LicenseShortName", {}).get("value", "")
                ).strip()

                # Geen dubbele foto's binnen dezelfde video.
                url = info.get("thumburl") or info.get("url")
                if not url or url in USED_IMAGES or not license_name:
                    continue

                # Vermijd logo's, posters met tekst en niet-foto's.
                excluded = [
                    "logo", "icon", "map", "diagram", "coat of arms",
                    "flag", "screenshot", "symbol"
                ]
                if any(word in title.lower() for word in excluded):
                    continue

                # Geef titels met relevante woorden een hogere score.
                overlap = len(query_words.intersection(title_words))
                theme_words = set(re.findall(r"[a-z]+", theme))
                theme_bonus = len(theme_words.intersection(title_words))

                scored.append((
                    overlap + theme_bonus,
                    page,
                    info,
                    license_name,
                    url
                ))

            # Probeer de best passende resultaten eerst.
            scored.sort(key=lambda item: item[0], reverse=True)

            # Kies willekeurig uit de beste resultaten om herhaling
            # van steeds dezelfde eerste zoekuitkomst te verminderen.
            best = [item for item in scored[:5] if item[0] > 0]
            random.shuffle(best)

            for score, page, info, license_name, url in best:
                try:
                    image_response = session.get(url, timeout=25)
                    image_response.raise_for_status()

                    image = Image.open(
                        BytesIO(image_response.content)
                    ).convert("RGB")

                    if image.width < 300 or image.height < 250:
                        continue

                    USED_IMAGES.add(url)

                    credit = (
                        f"{page.get('title', '')} | "
                        f"License: {license_name} | "
                        f"{info.get('descriptionurl', '')}"
                    )
                    print(f"Foto gevonden voor '{sentence}': {page.get('title')}")
                    return image, credit

                except Exception as exc:
                    print(f"Foto kon niet worden geopend: {exc}")

        except Exception as exc:
            print(f"Zoeken mislukt voor '{query}': {exc}")

    return None, None


# ==================================================
# 4. UNIEKE RESERVESCÈNE
# ==================================================

def load_font(size):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def draw_object_scene(sentence, theme, index):
    # Verschillende achtergronden voor meer afwisseling.
    random.seed(index + 100)
    background = random.choice([
        (7, 8, 16), (12, 9, 18), (10, 13, 22),
        (18, 10, 14), (8, 14, 17)
    ])

    image = Image.new("RGB", (W, H), background)
    draw = ImageDraw.Draw(image)

    # Donkere vloer en achtergrondlicht.
    draw.rectangle((0, 880, W, H), fill=(20, 17, 25))
    draw.ellipse((80, 180, 640, 950), fill=(25, 10, 20))

    if theme == "phone":
        draw.rectangle((100, 850, 620, 900), fill=(45, 35, 32))
        draw.rounded_rectangle((250, 430, 470, 800), radius=30,
                               fill=(35, 37, 45), outline=(150, 150, 160), width=5)
        draw.rounded_rectangle((270, 465, 450, 740), radius=10, fill=(60, 90, 115))
        draw.ellipse((335, 500, 385, 550), fill=(220, 225, 240))

    elif theme in ("door", "hallway", "closet", "stairs", "house"):
        draw.rectangle((100, 180, 620, 1050), fill=(30, 24, 30))
        if theme == "stairs":
            for step in range(7):
                y = 850 - step * 90
                x = 140 + step * 40
                draw.polygon([(x, y), (600, y), (600, y + 35), (x, y + 35)],
                             fill=(65, 45, 42))
        else:
            draw.rectangle((200, 260, 520, 1000), fill=(12, 10, 16),
                           outline=(105, 80, 75), width=8)
            draw.ellipse((455, 590, 475, 610), fill=(180, 145, 90))

    elif theme == "window":
        draw.rectangle((140, 250, 580, 800), fill=(10, 15, 30),
                       outline=(140, 135, 145), width=9)
        draw.line((360, 250, 360, 800), fill=(110, 110, 130), width=7)
        draw.line((140, 525, 580, 525), fill=(110, 110, 130), width=7)
        draw.ellipse((360, 370, 430, 440), fill=(55, 55, 75))

    elif theme == "mirror":
        draw.rounded_rectangle((170, 220, 550, 850), radius=70,
                               fill=(40, 45, 55), outline=(150, 125, 105), width=12)
        draw.ellipse((285, 340, 435, 500), fill=(12, 12, 20))
        draw.polygon([(250, 780), (290, 520), (430, 520), (470, 780)],
                     fill=(16, 16, 25))

    elif theme == "photograph":
        draw.rectangle((150, 280, 570, 850), fill=(95, 70, 48))
        draw.rectangle((180, 310, 540, 820), fill=(22, 25, 35))
        draw.ellipse((285, 390, 435, 540), fill=(48, 42, 48))
        draw.polygon([(230, 770), (280, 535), (440, 535), (490, 770)],
                     fill=(38, 34, 42))

    elif theme == "footprints":
        for x, y in [(270, 400), (390, 510), (270, 620),
                     (390, 730), (270, 840)]:
            draw.ellipse((x, y, x + 45, y + 75), fill=(55, 35, 35))

    else:
        # Eigen silhouet met wisselende plaats en grootte.
        x = random.randint(230, 330)
        draw.ellipse((x, 330, x + 160, 500), fill=(3, 3, 8))
        draw.polygon([
            (x - 45, 1000), (x - 5, 500),
            (x + 165, 500), (x + 220, 1000)
        ], fill=(3, 3, 8))

    return image


# ==================================================
# 5. TEKST OP DE AFBEELDING
# ==================================================

def create_scene(sentence, index, credits):
    theme = choose_theme(sentence)
    image, credit = search_photo(sentence, theme)

    if image is None:
        print(f"Geen geschikte foto voor scène {index + 1}; illustratie gebruiken.")
        image = draw_object_scene(sentence, theme, index)
        credits.append(
            f"Scène {index + 1}: zelfgemaakte illustratie ({theme})"
        )
    else:
        image.thumbnail((W, H))

        canvas = Image.new("RGB", (W, H), (8, 8, 16))
        canvas.paste(
            image,
            ((W - image.width) // 2, (H - image.height) // 2)
        )
        image = ImageEnhance.Brightness(canvas).enhance(0.52)
        credits.append(f"Scène {index + 1}: {credit}")

    image = image.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 55))
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    font = load_font(39)
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

    line_height = 55
    total_height = len(lines) * line_height
    y = (H - total_height) // 2

    draw.rounded_rectangle(
        (35, y - 25, W - 35, y + total_height + 25),
        radius=20,
        fill=(0, 0, 0, 190)
    )

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height

    draw.text((30, 35), "DARK TALES", font=small_font,
              fill=(230, 200, 200))

    image.convert("RGB").save(FRAMES / f"frame_{index + 1:02d}.png")


# ==================================================
# 6. VIDEO MAKEN
# ==================================================

def main():
    # Voorkom hergebruik van afbeeldingen uit een vorige uitvoering.
    USED_IMAGES.clear()

    for old_frame in FRAMES.glob("frame_*.png"):
        old_frame.unlink()

    story = generate_story()

    # Zorg dat er precies 12 scènes zijn.
    story = story[:SCENES]
    if len(story) < SCENES:
        story.extend(FALLBACK_STORY[len(story):SCENES])

    print("\nVerhaal:")
    for i, sentence in enumerate(story, start=1):
        print(f"{i}. {sentence}")

    print("\nEngelse vertelling maken...")
    gTTS(text=" ".join(story), lang="en", slow=False).save("narration.mp3")

    credits = []

    for i, sentence in enumerate(story):
        print(f"\nScène {i + 1}/{SCENES}: {sentence}")
        create_scene(sentence, i, credits)

    Path("image-credits.txt").write_text(
        "\n\n".join(credits), encoding="utf-8"
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
        "-movflags", "+faststart", str(OUT)
    ]

    subprocess.run(command, check=True)

    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("De video is niet goed aangemaakt.")

    print(f"\nVideo klaar: {OUT}")
    print("Afbeeldingsbronnen en licenties staan in image-credits.txt")


if __name__ == "__main__":
    main()
