import os
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not configured")

client = genai.Client(api_key=api_key)

prompt = """Write one original English horror story for a YouTube Short.
Length: 100-130 words.
Start with a gripping hook in the first sentence.
Build suspense and finish with an unexpected twist.
Use fictional characters and original wording.
Return only the story, without a title or commentary."""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
)

story = response.text
if not story:
    raise RuntimeError("The AI returned an empty story")

with open("story.txt", "w", encoding="utf-8") as file:
    file.write(story)

print(story)
