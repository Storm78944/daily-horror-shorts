
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
    "User-Agent": "DarkTalesEducationalProject/3.0 (video project)"
})

USED_IMAGES = set()

FALLBACK_STORY = [
    "A phone displayed a strange message on a wooden table.",
    "A bedroom door slowly opened into a dark hallway.",
    "A human silhouette appeared behind a rain-covered window.",
    "Muddy footprints crossed the dusty wooden floor.",
    "An old family photograph showed an unfamiliar face.",
    "A flickering lamp lit an abandoned living room.",
    "A phone received a message from an unknown number.",
    "The message contained a photograph of a staircase.",
    "A tall shadow stood at the top of the stairs.",
    "An antique mirror reflected a figure behind the viewer.",
    "Three fresh scratches appeared on a closed wardrobe.",
    "The ringing phone displayed the owner's own name."
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
        combined = " ".join(lines)
        lines = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", combined)
            if part.strip()
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
                    "content": (
                        "Write original, suspenseful horror stories. "
                        "Each scene must be visually specific and different. "
                        "Use concrete subjects, actions, objects and locations."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        "Write an original English horror story for a YouTube Short. "
                        "Return exactly 12 numbered sentences, one per line. "
                        "Each sentence describes one clear visual moment that could "
                        "be illustrated by a photograph. Include the main subject, "
                        "what it is doing, and the setting. Vary locations and objects. "
                        "Avoid vague descriptions such as 'something strange happened'. "
                        "End with a surprising twist. No title or explanations. "
                        "Keep the story suitable for a general audience."
                    )
                }
            ],
            temperature=0.9,
            max_completion_tokens=1400,
        )

        story = split_story(response.choices[0].message.content or "")
        if len(story) >= SCENES:
            return story[:SCENES]

        print("AI gaf te weinig scènes; reserveverhaal gebruiken.")

    except Exception as exc:
        print(f"AI-verhaal niet beschikbaar: {exc}")

    return FALLBACK_STORY.copy()


# ==================================================
# 2. SCÈNE HERKENNEN
# ==================================================

SCENE_RULES = [
    ("footprints", ["footprints", "footprint", "muddy tracks", "shoe prints"]),
    ("message", ["message", "text message", "unknown number", "notification"]),
    ("phone", ["phone", "telephone", "mobile", "caller", "ringing"]),
    ("photograph", ["photograph", "photographs", "family photo", "portrait"]),
    ("stairs", ["staircase", "stairs", "steps", "top of the stairs"]),
    ("mirror", ["mirror", "reflection", "reflected"]),
    ("window", ["window", "rain-covered glass", "curtains"]),
    ("wardrobe", ["wardrobe", "closet", "cupboard"]),
    ("door", ["doorway", "door handle", "door opened", "closed door", "door"]),
    ("hallway", ["hallway", "corridor", "passage"]),
    ("bedroom", ["bedroom", "bedside", "pillow"]),
    ("lamp", ["lamp", "light bulb", "flickering light", "chandelier"]),
    ("house", ["abandoned house", "haunted house", "old building", "living room"]),
    ("shadow", ["shadow", "silhouette", "stranger", "tall figure", "unknown figure"]),
]

SCENE_SEARCH_TERMS = {
    "footprints": [
        "muddy footprints on dusty wooden floor photograph",
        "muddy shoe prints inside abandoned house",
        "footprints on old floor close up"
    ],
    "message": [
        "smartphone screen showing text message photograph",
        "phone displaying text notification in dark room",
        "close up mobile phone message screen"
    ],
    "phone": [
        "smartphone glowing on wooden table at night",
        "telephone ringing in dark room photograph",
        "mobile phone on bedside table at night"
    ],
    "photograph": [
        "old framed family photograph on table",
        "vintage family portrait in old picture frame",
        "aged photograph close up"
    ],
    "stairs": [
        "dark wooden staircase inside old house",
        "staircase leading into darkness photograph",
        "old narrow stairs in abandoned building"
    ],
    "mirror": [
        "antique mirror in dark bedroom photograph",
        "old mirror reflecting an empty room",
        "ornate mirror in abandoned house"
    ],
    "window": [
        "human silhouette behind window at night",
        "rain covered window dark house photograph",
        "shadow visible through old house window"
    ],
    "wardrobe": [
        "old wooden wardrobe in dark bedroom",
        "open antique closet in abandoned house",
        "closed wardrobe in dimly lit room"
    ],
    "door": [
        "old wooden door opening into dark hallway",
        "open doorway inside abandoned house",
        "old door handle in dim light photograph"
    ],
    "hallway": [
        "long dark hallway in abandoned house",
        "empty corridor with dim lighting photograph",
        "narrow corridor inside old building"
    ],
    "bedroom": [
        "abandoned bedroom at night photograph",
        "old bedroom with bed and dark shadows",
        "dark bedroom interior realistic photograph"
    ],
    "lamp": [
        "single flickering lamp in dark room",
        "old table lamp illuminating dusty room",
        "dim lamp inside abandoned house"
    ],
    "house": [
        "abandoned house exterior at night photograph",
        "old deserted house surrounded by fog",
        "abandoned living room dark interior"
    ],
    "shadow": [
        "human silhouette standing in dark doorway",
        "tall shadowy figure in abandoned hallway",
        "mysterious human silhouette at night"
    ],
    "unknown": [
        "eerie abandoned house interior photograph",
        "dark atmospheric old building interior",
        "empty room with mysterious shadows"
    ]
}

STOPWORDS = set("""
the and with from into onto then there that this was were had has have
for while when where someone something appeared slowly suddenly again
inside outside showed started began looked could would their his her its
they him she after before under over near one two three old dark empty
a an is in on at of to by as it who what
""".split())


def choose_theme(sentence):
    text = sentence.lower()

    # De meest specifieke gebeurtenissen staan bovenaan.
    for theme, keywords in SCENE_RULES:
        if any(re.search(r"\b" + re.escape(word) + r"\b", text)
               for word in keywords):
            return theme

    return "unknown"


def make_queries(sentence, theme):
    queries = list(SCENE_SEARCH_TERMS.get(
        theme, SCENE_SEARCH_TERMS["unknown"]
    ))

    # Gebruik ook de belangrijkste woorden uit de verhaalzin.
    words = re.findall(r"[a-z]+", sentence.lower())
    important = [
        word for word in words
        if len(word) >= 4 and word not in STOPWORDS
    ]

    if important:
        queries.append(" ".join(important[:6]) + " photograph")

    return list(dict.fromkeys(queries))


# ==================================================
# 3. PASSENDE FOTO ZOEKEN
# ==================================================

EXCLUDED_WORDS = [
    "logo", "icon", "coat of arms", "diagram",
    "screenshot", "map", "flag", "symbol"
]


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
                    "gsrlimit": 20,
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 900,
                    "format": "json",
                },
                timeout=25,
            )
            response.raise_for_status()

            pages = list(
                response.json().get("query", {}).get("pages", {}).values()
            )

            scored = []
            query_words = set(re.findall(r"[a-z]+", query.lower()))
            query_words -= STOPWORDS

            for page in pages:
                title = page.get("title", "").lower()

                if any(word in title for word in EXCLUDED_WORDS):
                    continue

                info_list = page.get("imageinfo", [])
                if not info_list:
                    continue

                info = info_list[0]
                metadata = info.get("extmetadata", {})

                license_name = unescape(
                    metadata.get("LicenseShortName", {}).get("value", "")
                ).strip()

                url = info.get("thumburl") or info.get("url")

                if not url or url in USED_IMAGES or not license_name:
                    continue

                title_words = set(re.findall(r"[a-z]+", title))
                overlap = len(query_words & title_words)

                # Geef zoekresultaten die het onderwerp benoemen voorrang.
                theme_words = set(theme.split())
                theme_bonus = 2 if theme_words & title_words else 0

                # Geef resultaten zonder enige relevante titelwoorden
                # geen voorrang boven betere resultaten.
                if overlap == 0 and theme != "unknown":
                    continue

                scored.append((overlap + theme_bonus, page, info,
                               license_name, url))

            scored.sort(key=lambda item: item[0], reverse=True)

            # Eerst de best passende kandidaten proberen.
            # Een kleine willekeurige keuze helpt tegen steeds dezelfde foto.
            best = scored[:8]
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

                    print(
                        f"Foto voor scène: {page.get('title', '')}"
                    )
                    return image, credit

                except Exception as exc:
                    print(f"Foto overslaan: {exc}")

        except Exception as exc:
            print(f"Zoekopdracht mislukt '{query}': {exc}")

    return None, None


# ==================================================
# 4. RESERVE-ILLUSTRATIES
# ==================================================

def load_font(size):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def draw_object_scene(sentence, theme, index):
    random.seed(index + 100)
    background = random.choice([
        (7, 8, 16), (12, 9, 18), (10, 13, 22),
        (18, 10, 14), (8, 14, 17)
    ])

    image = Image.new("RGB", (W, H), background)
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 880, W, H), fill=(20, 17, 25))
    draw.ellipse((80, 180, 640, 950), fill=(25, 10, 20))

    if theme in ("phone", "message"):
        draw.rectangle((80, 850, 640, 900), fill=(45, 35, 32))
        draw.rounded_rectangle(
            (245, 400, 475, 810), radius=30,
            fill=(35, 37, 45), outline=(150, 150, 160), width=5
        )
        draw.rounded_rectangle(
            (265, 445, 455, 750), radius=10, fill=(35, 65, 85)
        )

        if theme == "message":
            for y in (500, 560, 620):
                draw.rounded_rectangle(
                    (285, y, 430, y + 25), radius=8, fill=(100, 160, 180)
                )
        else:
            draw.ellipse((335, 470, 385, 520), fill=(220, 225, 240))

    elif theme in ("door", "hallway", "wardrobe", "stairs", "house"):
        draw.rectangle((100, 180, 620, 1050), fill=(30, 24, 30))

        if theme == "stairs":
            for step in range(7):
                y = 850 - step * 90
                x = 140 + step * 40
                draw.polygon(
                    [(x, y), (600, y), (600, y + 35), (x, y + 35)],
                    fill=(65, 45, 42)
                )
        else:
            draw.rectangle(
                (200, 260, 520, 1000), fill=(12, 10, 16),
                outline=(105, 80, 75), width=8
            )
            draw.ellipse((455, 590, 475, 610), fill=(180, 145, 90))

    elif theme == "window":
        draw.rectangle(
            (140, 250, 580, 800), fill=(10, 15, 30),
            outline=(140, 135, 145), width=9
        )
        draw.line((360, 250, 360, 800), fill=(110, 110, 130), width=7)
        draw.line((140, 525, 580, 525), fill=(110, 110, 130), width=7)
        draw.ellipse((360, 370, 430, 440), fill=(55, 55, 75))

    elif theme == "mirror":
        draw.rounded_rectangle(
            (170, 220, 550, 850), radius=70,
            fill=(40, 45, 55), outline=(150, 125, 105), width=12
        )
        draw.ellipse((285, 340, 435, 500), fill=(12, 12, 20))

    elif theme == "photograph":
        draw.rectangle((150, 280, 570, 850), fill=(95, 70, 48))
        draw.rectangle((180, 310, 540, 820), fill=(22, 25, 35))
        draw.ellipse((285, 390, 435, 540), fill=(48, 42, 48))

    elif theme == "footprints":
        for x, y in [
            (270, 400), (390, 510), (270, 620),
            (390, 730), (270, 840)
        ]:
            draw.ellipse((x, y, x + 45, y + 75), fill=(55, 35, 35))

    else:
        x = random.randint(230, 330)
        draw.ellipse((x, 330, x + 160, 500), fill=(3, 3, 8))
        draw.polygon(
            [(x - 45, 1000), (x - 5, 500),
             (x + 165, 500), (x + 220, 1000)],
            fill=(3, 3, 8)
        )

    return image


# ==================================================
# 5. SCÈNE EN TEKST MAKEN
# ==================================================

def create_scene(sentence, index, credits):
    theme = choose_theme(sentence)
    image, credit = search_photo(sentence, theme)

    if image is None:
        print(f"Scène {index + 1}: reserve-illustratie gebruiken.")
        image = draw_object_scene(sentence, theme, index)
        credits.append(
            f"Scène {index + 1}: zelfgemaakte illustratie ({theme})"
        )
    else:
        # Vul het volledige verticale beeld zonder de foto uit te rekken.
        image.thumbnail((W, H))

        canvas = Image.new("RGB", (W, H), (8, 8, 16))
        canvas.paste(
            image,
            ((W - image.width) // 2, (H - image.height) // 2)
        )
        image = ImageEnhance.Brightness(canvas).enhance(0.65)
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
        radius=20, fill=(0, 0, 0, 190)
    )

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x + 2, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_height

    draw.text(
        (30, 35), "DARK TALES",
        font=small_font, fill=(230, 200, 200)
    )

    image.convert("RGB").save(FRAMES / f"frame_{index + 1:02d}.png")


# ==================================================
# 6. VIDEO MAKEN
# ==================================================

def main():
    USED_IMAGES.clear()

    for old_frame in FRAMES.glob("frame_*.png"):
        old_frame.unlink()

    story = generate_story()
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
    print("Afbeeldingsbronnen staan in image-credits.txt")


if __name__ == "__main__":
    main()
