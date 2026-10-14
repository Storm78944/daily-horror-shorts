
import os
import re
import json
import random
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests
from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

# =========================================================
# DARK TALES - AUTOMATISCHE HORROR SHORTS
# GROQ_API_KEY blijft je bestaande verhaal-secret.
# POLLINATIONS_API_KEY is optioneel voor AI-afbeeldingen.
# Zonder die extra sleutel probeert het script foto's te vinden.
# =========================================================

OUT = Path("horror-short.mp4")
FRAMES = Path("frames")
FRAMES.mkdir(exist_ok=True)

W, H = 720, 1280
SCENES = 12
SECONDS_PER_SCENE = 5
MODEL = "openai/gpt-oss-120b"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "DarkTalesVideoProject/1.0 (personal video project)"
})

USED_IMAGE_URLS = set()

FALLBACK_STORY = [
    "At midnight, my phone lit up with a message from my missing sister.",
    "The message said she was standing outside my house.",
    "I looked through the window, but the street was completely empty.",
    "Another message arrived: stop looking outside.",
    "A muddy footprint appeared on the floor behind me.",
    "I turned toward the dark hallway and heard someone whisper my name.",
    "My bedroom door slowly opened by itself.",
    "At the end of the hallway stood a figure wearing my sister's coat.",
    "My phone buzzed again, showing a photograph of my bedroom.",
    "In the photograph, someone was standing directly behind me.",
    "I turned around, but nobody was there.",
    "Then my phone displayed one final message: do not turn around again."
]

# Zoektermen zijn bewust concreet: liever een passend voorwerp
# dan een willekeurige foto die alleen "eng" lijkt.
THEMES = [
    ("phone", ["phone", "message", "text", "screen", "call"]),
    ("window", ["window", "outside", "street", "looking"]),
    ("footprint", ["footprint", "footprints", "muddy", "shoe"]),
    ("hallway", ["hallway", "corridor", "whisper", "dark"]),
    ("door", ["door", "opened", "opening", "bedroom"]),
    ("figure", ["figure", "silhouette", "person", "standing"]),
    ("photo", ["photograph", "picture", "photo", "image"]),
    ("mirror", ["mirror", "reflection", "reflected"]),
    ("bedroom", ["bedroom", "bed", "room", "behind"]),
    ("house", ["house", "home", "building", "outside"]),
    ("shadow", ["shadow", "darkness", "dark", "shape"]),
]

SEARCHES = {
    "phone": [
        "smartphone on dark table photograph",
        "phone screen in dark room photograph",
        "mobile phone close up at night"
    ],
    "window": [
        "dark house window at night photograph",
        "empty street outside window at night",
        "rain on window at night photograph"
    ],
    "footprint": [
        "muddy footprints on wooden floor photograph",
        "muddy shoe prints on floor close up",
        "footprints in dark hallway photograph"
    ],
    "hallway": [
        "long dark empty hallway photograph",
        "dark corridor in old house photograph",
        "dimly lit hallway at night"
    ],
    "door": [
        "old wooden door in dark hallway photograph",
        "half open bedroom door at night",
        "dark doorway in an empty house"
    ],
    "figure": [
        "human silhouette standing in doorway photograph",
        "person silhouette behind frosted glass",
        "distant human silhouette in dark hallway"
    ],
    "photo": [
        "old photograph lying on wooden table",
        "framed family photograph in dark room",
        "old photo close up photograph"
    ],
    "mirror": [
        "old mirror in dark room photograph",
        "mirror reflecting empty bedroom",
        "mirror in dimly lit hallway"
    ],
    "bedroom": [
        "dark empty bedroom at night photograph",
        "bedroom with open door at night",
        "unmade bed in dimly lit room"
    ],
    "house": [
        "isolated old house at night photograph",
        "abandoned house exterior at night",
        "old house in fog at night"
    ],
    "shadow": [
        "long shadow on wall in dark room",
        "human shaped shadow on wall photograph",
        "dark silhouette on wall at night"
    ],
    "general": [
        "foggy forest at night photograph",
        "dark abandoned building photograph",
        "empty street in fog at night"
    ],
}


def get_font(size):
    """Zoek een beschikbaar lettertype op GitHub Actions."""
    options = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for name in options:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_story():
    """Maak precies 12 korte, visuele scènes met Groq."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY ontbreekt; ik gebruik het reserveverhaal.")
        return FALLBACK_STORY[:]

    prompt = f"""
Write an original short horror story for a vertical video.
Return exactly {SCENES} numbered lines, in English.
Each line must be one short sentence describing a scene that can be
shown clearly in a photograph or cinematic image.
Use concrete visible objects, locations, actions, and people.
Avoid abstract feelings and vague descriptions.
Keep the story coherent, tense, and suitable for a general audience.
No title, no explanation, no markdown.
"""

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=900,
        )
        raw = response.choices[0].message.content or ""
        lines = []

        for line in raw.splitlines():
            line = re.sub(r"^\s*(?:\d+[\.\):\-]\s*|[-*]\s*)", "", line)
            line = line.strip().strip('"')
            if len(line) > 12:
                lines.append(line)

        if len(lines) >= SCENES:
            return lines[:SCENES]

        print("Het verhaal had te weinig scènes; reserveverhaal gebruikt.")
    except Exception as exc:
        print(f"Verhaal maken lukte niet: {exc}")

    return FALLBACK_STORY[:]


def get_theme(sentence):
    """Bepaal het belangrijkste zichtbare onderwerp van de scène."""
    text = sentence.lower()
    for theme, words in THEMES:
        if any(word in text for word in words):
            return theme
    return "general"


def make_ai_prompt(sentence, theme):
    """Maak een concrete prompt voor één afbeelding."""
    visual = {
        "phone": "a close-up of a smartphone in a dark room",
        "window": "a window looking onto an empty street at night",
        "footprint": "clear muddy footprints on a floor",
        "hallway": "a long, empty, dimly lit hallway",
        "door": "a partly open old door in a dark house",
        "figure": "a distant human silhouette in a doorway",
        "photo": "an old photograph lying on a table",
        "mirror": "a mirror in a dimly lit room",
        "bedroom": "a dark bedroom with realistic furniture",
        "house": "an isolated old house at night",
        "shadow": "a mysterious human-shaped shadow on a wall",
        "general": "a realistic eerie location at night",
    }.get(theme, "a realistic eerie location at night")

    return (
        f"Cinematic realistic horror still. The scene must clearly show: "
        f"{sentence}. Main visual subject: {visual}. "
        "Photorealistic, coherent composition, believable real-world objects, "
        "dark blue and muted red lighting, subtle fog, unsettling atmosphere, "
        "high detail, no text, no letters, no captions, no watermark, "
        "vertical 9:16 composition."
    )


def generate_ai_image(sentence, theme, index):
    """
    Gebruik AI-afbeeldingen als POLLINATIONS_API_KEY is ingesteld.
    Deze functie is optioneel: een fout stopt de videomaker niet.
    Gratis gebruik of beschikbaarheid wordt niet gegarandeerd.
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    if not api_key:
        return None

    prompt = make_ai_prompt(sentence, theme)
    url = "https://gen.pollinations.ai/image/" + quote(prompt, safe="")
    params = {
        "model": "flux",
        "width": 768,
        "height": 1365,
        "seed": random.randint(1, 2_000_000_000),
    }

    try:
        response = SESSION.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(15, 120),
        )
        response.raise_for_status()

        if not response.headers.get("content-type", "").startswith("image/"):
            print(f"AI-afbeelding {index + 1}: geen afbeelding ontvangen.")
            return None

        image = Image.open(__import__("io").BytesIO(response.content)).convert("RGB")
        if image.width < 200 or image.height < 200:
            return None

        path = FRAMES / f"source_{index + 1:02d}.jpg"
        image.save(path, quality=92)
        print(f"AI-afbeelding gemaakt voor scène {index + 1}.")
        return path
    except Exception as exc:
        print(f"AI-afbeelding {index + 1} niet beschikbaar: {exc}")
        return None


def search_wikimedia_photo(sentence, theme, index):
    """Zoek een foto via Wikimedia Commons en vermijd herhaling."""
    queries = SEARCHES.get(theme, SEARCHES["general"])
    candidates = []

    for query in queries:
        try:
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": 6,
                "gsrlimit": 12,
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
                "iiurlwidth": 1000,
                "format": "json",
            }
            response = SESSION.get(
                "https://commons.wikimedia.org/w/api.php",
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})

            for page in pages.values():
                title = page.get("title", "").lower()
                info = (page.get("imageinfo") or [{}])[0]
                image_url = info.get("thumburl") or info.get("url")

                if not image_url or image_url in USED_IMAGE_URLS:
                    continue

                if not image_url.lower().split("?")[0].endswith(
                    (".jpg", ".jpeg", ".png", ".webp")
                ):
                    continue

                # Vermijd meestal ongeschikte bestanden.
                if any(word in title for word in [
                    "map", "logo", "flag", "diagram", "icon", "coat of arms",
                    "screenshot", "poster", "collage", "svg", "chart"
                ]):
                    continue

                width = info.get("width", 0)
                height = info.get("height", 0)
                if width < 500 or height < 400:
                    continue

                # Titels die onderwerpwoorden bevatten krijgen voorrang.
                words = set(re.findall(r"[a-z]{4,}", sentence.lower()))
                title_words = set(re.findall(r"[a-z]{4,}", title))
                overlap = len(words & title_words)
                candidates.append((overlap, title, image_url, info))
        except Exception as exc:
            print(f"Foto zoeken lukte niet voor '{query}': {exc}")

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: item[0], reverse=True)
    # Kies uit de best passende resultaten, niet uit de volledige lijst.
    shortlist = candidates[:5]
    random.shuffle(shortlist)

    for score, title, image_url, info in shortlist:
        try:
            response = SESSION.get(image_url, timeout=25)
            response.raise_for_status()
            from io import BytesIO
            image = Image.open(BytesIO(response.content)).convert("RGB")

            if image.width < 300 or image.height < 250:
                continue

            USED_IMAGE_URLS.add(image_url)
            metadata = info.get("extmetadata", {})
            artist = metadata.get("Artist", {}).get("value", "Onbekend")
            license_name = metadata.get("LicenseShortName", {}).get(
                "value", "Licentie controleren"
            )
            page_url = info.get("descriptionurl", "")

            credit = (
                f"Scène {index + 1}: {title}; "
                f"maker: {artist}; licentie: {license_name}; "
                f"bron: {page_url}"
            )
            return image, credit
        except Exception:
            continue

    return None, None


def draw_fallback_image(sentence, theme, index):
    """Maak een donkere illustratie als er geen bruikbare afbeelding is."""
    image = Image.new("RGB", (W, H), (8, 9, 17))
    draw = ImageDraw.Draw(image)

    # Subtiele rode gloed.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((70, 180, 650, 800), fill=(80, 5, 20, 85))
    glow = glow.filter(ImageFilter.GaussianBlur(80))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(image)

    if theme == "phone":
        draw.rounded_rectangle((245, 360, 475, 790), radius=30,
                               fill=(24, 25, 33), outline=(120, 120, 135), width=5)
        draw.rounded_rectangle((265, 400, 455, 730), radius=12, fill=(25, 40, 50))
        draw.rounded_rectangle((285, 460, 435, 540), radius=12, fill=(55, 75, 85))
    elif theme in ("door", "hallway", "bedroom", "house"):
        draw.rectangle((190, 250, 530, 920), fill=(18, 19, 28),
                       outline=(95, 75, 72), width=8)
        draw.rectangle((220, 280, 500, 900), fill=(7, 8, 14))
        if theme == "door":
            draw.ellipse((450, 590, 470, 610), fill=(180, 145, 90))
        if theme == "hallway":
            for offset in range(0, 5):
                x = 240 + offset * 35
                draw.line((360, 320, x, 900), fill=(40, 38, 48), width=3)
    elif theme == "window":
        draw.rectangle((120, 260, 600, 780), fill=(15, 20, 34),
                       outline=(90, 85, 95), width=12)
        draw.line((360, 270, 360, 770), fill=(90, 85, 95), width=8)
        draw.line((130, 520, 590, 520), fill=(90, 85, 95), width=8)
        draw.ellipse((450, 330, 490, 370), fill=(165, 165, 175))
    elif theme == "footprint":
        for y in range(320, 850, 120):
            x = 250 if (y // 120) % 2 else 410
            draw.ellipse((x, y, x + 65, y + 110), fill=(50, 35, 32))
    elif theme == "figure":
        draw.ellipse((300, 320, 420, 450), fill=(3, 4, 8))
        draw.polygon([(280, 470), (440, 470), (490, 900), (230, 900)],
                     fill=(3, 4, 8))
    elif theme == "mirror":
        draw.rounded_rectangle((150, 250, 570, 850), radius=100,
                               fill=(70, 75, 88), outline=(130, 105, 90), width=15)
        draw.rectangle((190, 290, 530, 810), fill=(12, 16, 28))
    elif theme == "photo":
        draw.rectangle((180, 330, 540, 700), fill=(80, 72, 60),
                       outline=(170, 145, 100), width=12)
        draw.rectangle((205, 355, 515, 675), fill=(30, 35, 42))
        draw.ellipse((315, 405, 405, 495), fill=(8, 10, 15))
        draw.polygon([(260, 650), (320, 500), (400, 590), (460, 510), (500, 650)],
                     fill=(8, 10, 15))
    else:
        draw.ellipse((140, 280, 580, 800), fill=(15, 17, 27))
        draw.rectangle((180, 650, 540, 900), fill=(12, 13, 21))

    return image


def fit_cover(image, size=(W, H)):
    """Vul het verticale beeld zonder uitgerekte gezichten of objecten."""
    target_w, target_h = size
    ratio = max(target_w / image.width, target_h / image.height)
    new_size = (int(image.width * ratio), int(image.height * ratio))
    image = image.resize(new_size, Image.Resampling.LANCZOS)
    left = (image.width - target_w) // 2
    top = (image.height - target_h) // 2
    return image.crop((left, top, left + target_w, top + target_h))


def add_caption(image, sentence):
    """Maak de scène donker genoeg en zet leesbare tekst onderaan."""
    image = ImageEnhance.Brightness(image).enhance(0.58)
    image = ImageEnhance.Color(image).enhance(0.75)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 850, W, H), fill=(0, 0, 0, 165))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image)

    font = get_font(39)
    words = sentence.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= W - 80:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    # Maximaal vier regels zodat de tekst in beeld blijft.
    if len(lines) > 4:
        lines = lines[:3] + [" ".join(lines[3:])]
    y = 900
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=2)
        text_w = bbox[2] - bbox[0]
        x = max(30, (W - text_w) // 2)
        draw.text(
            (x, y), line, font=font, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255)
        )
        y += 60

    return image.convert("RGB")


def create_scene(sentence, index, credits):
    theme = get_theme(sentence)
    image = None

    # 1. Probeer eerst een echte AI-afbeelding, als de sleutel bestaat.
    ai_path = generate_ai_image(sentence, theme, index)
    if ai_path:
        try:
            image = Image.open(ai_path).convert("RGB")
            credits.append(f"Scène {index + 1}: AI-afbeelding via Pollinations")
        except Exception:
            image = None

    # 2. Anders een concrete foto uit Wikimedia Commons.
    if image is None:
        image, credit = search_wikimedia_photo(sentence, theme, index)
        if credit:
            credits.append(credit)

    # 3. Laat de video niet mislukken als er geen foto is gevonden.
    if image is None:
        print(f"Geen geschikte foto voor scène {index + 1}; illustratie gebruikt.")
        image = draw_fallback_image(sentence, theme, index)
        credits.append(f"Scène {index + 1}: zelfgemaakte illustratie")

    image = fit_cover(image)
    image = add_caption(image, sentence)
    frame_path = FRAMES / f"scene_{index + 1:02d}.jpg"
    image.save(frame_path, quality=92)
    return frame_path


def main():
    # Oude bestanden opruimen, zodat de video geen oude scènes gebruikt.
    for pattern in ("scene_*.jpg", "source_*.jpg"):
        for path in FRAMES.glob(pattern):
            path.unlink()

    for path in (OUT, Path("narration.mp3"), Path("image-credits.txt")):
        if path.exists():
            path.unlink()

    story = generate_story()
    story = story[:SCENES]

    while len(story) < SCENES:
        story.append(FALLBACK_STORY[len(story) % len(FALLBACK_STORY)])

    print("\nVerhaal:")
    for i, line in enumerate(story, 1):
        print(f"{i}. {line}")

    credits = []

    # Voice-over maken.
    narration_text = " ".join(story)
    try:
        gTTS(text=narration_text, lang="en", slow=False).save("narration.mp3")
    except Exception as exc:
        raise RuntimeError(
            f"De Engelse verteller kon niet worden gemaakt: {exc}"
        ) from exc

    # Elke zin krijgt een eigen afbeelding.
    for index, sentence in enumerate(story):
        print(f"\nScène {index + 1}/{SCENES}: {sentence}")
        create_scene(sentence, index, credits)

    Path("image-credits.txt").write_text(
        "\n".join(credits) + "\n", encoding="utf-8"
    )

    # Eén beeld per scène, elk ongeveer 5 seconden.
    # FFmpeg moet beschikbaar zijn in je GitHub Actions-runner.
    command = [
        "ffmpeg", "-y",
        "-framerate", f"1/{SECONDS_PER_SCENE}",
        "-start_number", "1",
        "-i", str(FRAMES / "scene_%02d.jpg"),
        "-i", "narration.mp3",
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
               f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(OUT),
    ]

    print("\nVideo maken...")
    result = subprocess.run(command, text=True, capture_output=True)

    if result.returncode != 0:
        print(result.stdout[-3000:])
        print(result.stderr[-6000:])
        raise RuntimeError("FFmpeg kon de video niet maken.")

    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("FFmpeg heeft geen bruikbare video gemaakt.")

    print(f"\nKlaar! Video gemaakt: {OUT}")
    print("Afbeeldingscredits staan in image-credits.txt")


if __name__ == "__main__":
    main()
