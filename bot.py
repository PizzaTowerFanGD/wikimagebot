import requests
from mastodon import Mastodon
from PIL import Image
import os
from google import genai

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
MANUAL_RUN = os.getenv('MANUAL_RUN', 'false').lower() == 'true'

HEADERS = {
    "User-Agent": "wikimagebot.mastodon.social/1.0 (https://github.com/PizzaTowerFanGD/wikimagebot)"
}

client = genai.Client()

# loop until we get a valid image with usable format
while True:
    try:
        res = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "random",
                "grnnamespace": 6,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "format": "json"
            },
            headers=HEADERS
        )
        res.raise_for_status()
        data = res.json()

        page = next(iter(data['query']['pages'].values()))
        title = page['title']
        imageinfo = page.get('imageinfo', [])

        if imageinfo:
            imageinfo = sorted(imageinfo, key=lambda x: x['width'], reverse=True)
            info = imageinfo[0]
            image_url = info['url']
            if image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                break
            else:
                print(f"invalid file type: {image_url}. retrying...")
        else:
            print("no image info found. retrying...")
    except Exception as e:
        print(f"error fetching image: {e}. retrying...")

# download the image
file_extension = os.path.splitext(image_url)[1] or ".jpg"
temp_file = f"temp_image{file_extension}"

try:
    response = requests.get(image_url, stream=True, headers=HEADERS)
    response.raise_for_status()

    with open(temp_file, "wb") as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)

    with Image.open(temp_file) as img:
        if img.format.upper() != "JPEG":
            print(f"converting {img.format} to jpeg...")
            img = img.convert("RGB")
            temp_file = "temp.jpg"
            img.save(temp_file, "JPEG")
        else:
            os.rename(temp_file, "temp.jpg")
            temp_file = "temp.jpg"

except Exception as e:
    print(f"error processing image: {e}")
    exit(1)

# generate alt text with gemini
try:
    image = Image.open(temp_file)
    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=[image, "you are generating alt text for a mastodon bot that posts random wikipedia images. respond with only up to 2 concise english sentences describing the image for accessibility. do not include quotes, punctuation beyond normal grammar, introductions, explanations, or formatting. however, if there is text, you must include a transcript, and an english translation if not in english. — output only the alt text itself."]
    )
    description = response.text.strip() or "no description available"
except Exception as e:
    print(f"gemini alt generation failed: {e}")
    description = "no description available"

# post to mastodon
mastodon = Mastodon(
    access_token=MASTODON_TOKEN,
    api_base_url='https://mastodon.social'
)

media = mastodon.media_post(temp_file, description=description)

if MANUAL_RUN:
    status = f'Manually Triggered: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
else:
    status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'

mastodon.status_post(status=status, media_ids=[media], sensitive=True)
print("posted:", status)
