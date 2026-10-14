
import os
import re
import subprocess
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from groq import Groq
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# ==================================================
# DARK TALES - HORROR VIDEO GENERATOR
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
    "User-Agent": "DarkTalesVideoGenerator/1.0 (educational project)"
})

# ==================================================
# 1. VERHAAL MAKEN
# ==================================================

FALLBACK_STORY = [
    "At midnight, my phone rang in the empty house.",
    "The screen showed a picture of my bedroom door.",
    "Someone had written my name across the photograph.",
    "I looked up and saw the door slowly opening.",
    "A dark hallway stretched beyond the doorway.",
    "Then I heard footsteps coming from upstairs.",
    "My phone received another message from an unknown number.",
    "The message said that someone was standing behind me.",
    "I turned around and saw a figure near the window.",
    "The figure was holding a phone identical to mine.",
    "My phone rang again, but this time the caller was me.",
    "The figure smiled and whispered, you are finally home.",
]


def split_story(text):
    if not text:
        return []

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text).strip()

    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[\.\)\-:]|[-*•])\s*", "", line)
        line = line.strip()

        if line and not re.match(
            r"^(story|horror story|title)\s*:", line, re.I
        ):
            lines.append(line)

    if len(lines) < SCENES:
        cleaned = re.sub(r"\s+", " ", text).strip()
        lines = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", cleaned)
            if s.strip()
        ]

    return lines


def generate_story():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY ontbreekt. Controleer GitHub Secrets."
        )

    client = Groq(api_key=api_key)

    prompt = """
Write an original horror story in English for a YouTube Short.

Return exactly 12 numbered sentences, one per line.
Each sentence must describe a clear, VISUAL scene that can be
illustrated with a real photograph.
Describe concrete objects, places, and actions.
For example, say "A mobile phone lights up on a wooden table"
rather than "Something strange happens".
Make the scenes follow one coherent story.
Build suspense and finish with a surprising twist.
No title, no introduction, no extra explanation.
Keep the story suitable for a general audience.
"""

    for attempt in range(2):
        try:
            print(f"Generating story, attempt {attempt + 1}...")

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Write original visual horror stories. "
                            "Return exactly 12 numbered sentences."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_completion_tokens=1400,
            )

            text = response.choices[0].message.content or ""
            story = split_story(text)

            if len(story) >= SCENES:
                return story[:SCENES]

            print(f"Received only {len(story)} sentences.")

        except Exception as exc:
            print(f"Story generation failed: {exc}")

    print("Using backup story.")
    return FALLBACK_STORY.copy()


# ==================================================
# 2. AFBEELDINGEN ZOEKEN OP WIKIMEDIA COMMONS
# ==================================================

def search_commons(sentence):
    """
    Zoek foto's met onderwerpen uit de volledige scène.
    Geef alleen voorrang aan bestanden met bekende licenties.
    """

    # Gebruik de volledige zin als zoekopdracht.
    # Kortere woordenlijst als tweede poging.
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on",
        "at", "to", "of", "my", "his", "her", "their",
        "it", "was", "were", "is", "are", "with", "from",
        "then", "suddenly", "slowly", "i", "he", "she",
        "they", "you", "me", "this", "that", "as", "by",
    }

    words = re.findall(r"[a-zA-Z]{3,}", sentence.lower())
    keywords = [w for w in words if w not in stopwords]
    short_query = " ".join(keywords[:6])

    queries = [sentence, short_query]

    for search_query in queries:
        if not search_query:
            continue

        try:
            response = session.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": search_query,
                    "gsrnamespace": 6,
                    "gsrlimit": 10,
                    "gsrwhat": "text",
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 900,
                    "format": "json",
                },
                timeout=25,
            )
            response.raise_for_status()
            data = response.json()

            pages = data.get("query", {}).get("pages", {})
            candidates = list(pages.values())

            # Geef voorkeur aan bestanden met een bekende licentie.
            for page in candidates:
                info = page.get("imageinfo", [{}])[0]
                meta = info.get("extmetadata", {})
                license_name = meta.get(
                    "LicenseShortName", {}
                ).get("value", "")

                if not license_name:
                    continue

                image_url = info.get("thumburl") or info.get("url")
                if not image_url:
                    continue

                return {
                    "url": image_url,
                    "title": page.get("title", "Unknown image"),
                    "license": license_name,
                    "artist": meta.get("Artist", {}).get(
                        "value", "Unknown"
                    ),
                    "source": info.get("descriptionurl", ""),
                }

        except Exception as exc:
            print(f"Image search failed: {exc}")

    return None


def download_background(sentence, index, credits):
    print(f"Searching image for scene {index + 1}: {sentence}")

    result = search_commons(sentence)

    if result:
        try:
            response = session.get(result["url"], timeout=25)
            response.raise_for_status()

            image = Image.open(
                BytesIO(response.content)
            ).convert("RGB")

            # Vul het verticale scherm zonder het beeld uit te rekken.
            image.thumbnail((W, H))

            canvas = Image.new("RGB", (W, H), (8, 8, 15))
            x = (W - image.width) // 2
            y = (H - image.height) // 2
            canvas.paste(image, (x, y))

            image = ImageEnhance.Brightness(canvas).enhance(0.40)

            credits.append(
                f"Scene {index + 1}: {result['title']}\n"
                f"Artist: {result['artist']}\n"
                f"License: {result['license']}\n"
                f"Source: {result['source']}\n"
            )

            print(
                f"Image found: {result['title']} "
                f"({result['license']})"
            )
            return image

        except Exception as exc:
            print(f"Could not download image: {exc}")

    # Geen willekeurige foto gebruiken als de zoekopdracht mislukt.
    print("No suitable licensed image found; using dark background.")

    image = Image.new("RGB", (W, H), (8, 8, 15))
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 180, 640, 900), fill=(28, 5, 12))
    return image


# ==================================================
# 3. TEKST OP DE AFBEELDING ZETTEN
# ==================================================

def load_font(size):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def create_scene(sentence, index, credits):
    image = download_background(sentence, index, credits)
    image = image.convert("RGBA")

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 65))
    image = Image.alpha_composite(image, overlay)

    draw = ImageDraw.Draw(image)
    font = load_font(40)
    small_font = load_font(24)

    words = sentence.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()

        if draw.textbbox((0, 0), test, font=font)[2] > W - 100:
            if current:
                lines.append(current)
            current = word
        else:
            current = test

    if current:
        lines.append(current)

    line_height = 56
    total_height = len(lines) * line_height
    y = (H - total_height) // 2
    padding = 26

    draw.rounded_rectangle(
        (35, y - padding, W - 35, y + total_height + padding),
        radius=20,
        fill=(0, 0, 0, 185),
    )

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2

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
        fill=(230, 200, 200, 255),
    )

    image.convert("RGB").save(
        FRAMES / f"frame_{index + 1:02d}.png"
    )


# ==================================================
# 4. VIDEO MAKEN
# ==================================================

def main():
    story = generate_story()

    print("\nStory:")
    for i, sentence in enumerate(story, 1):
        print(f"{i}. {sentence}")

    print("\nCreating English narration...")
    narration = " ".join(story)
    gTTS(text=narration, lang="en", slow=False).save(
        "narration.mp3"
    )

    for old_frame in FRAMES.glob("frame_*.png"):
        old_frame.unlink()

    credits = []

    for i, sentence in enumerate(story):
        print(f"\nCreating scene {i + 1}/{SCENES}...")
        create_scene(sentence, i, credits)

    Path("image-credits.txt").write_text(
        "\n\n".join(credits) if credits else
        "No external images were used.",
        encoding="utf-8",
    )

    print("\nRendering video...")

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
        raise RuntimeError("The video was not created correctly.")

    print(f"\nVideo ready: {OUT}")
    print("Image credits saved to image-credits.txt")


if __name__ == "__main__":
    main()
