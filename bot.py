import requests
from mastodon import Mastodon
import os

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')

while True:
    # Fetch a random Wikipedia image
    res = requests.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "generator": "random",
        "grnnamespace": 6,  # Namespace 6 corresponds to files (including images)
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    })
    res.raise_for_status()
    data = res.json()

    # Get the random image and its URL
    page = next(iter(data['query']['pages'].values()))
    title = page['title']
    imageinfo = page.get('imageinfo', [])

    # Check if the imageinfo exists and the file type is valid
    if imageinfo:
        image_url = imageinfo[0]['url']
        if image_url.lower().endswith(('.jpg', '.jpeg', '.png')):
            # Valid image type found, break the loop
            break
        else:
            # Log invalid file type and retry
            print(f"Invalid file type: {image_url}. Retrying...")
    else:
        # Log missing imageinfo and retry
        print("No image info found. Retrying...")

# Download the valid image
image_url = imageinfo[0]['url']
img_data = requests.get(image_url).content
with open("temp.jpg", "wb") as f:
    f.write(img_data)

# Post to Mastodon
mastodon = Mastodon(
    access_token=MASTODON_TOKEN,
    api_base_url='https://mastodon.social'
)

media = mastodon.media_post("temp.jpg")
status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
mastodon.status_post(status=status, media_ids=[media], sensitive=True)

print("posted:", status)
