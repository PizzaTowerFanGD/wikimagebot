import requests
from mastodon import Mastodon
import os

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')

# Fetch a random image instead of an article
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
if not imageinfo:
    print("No image info found")
    exit(0)

image_url = imageinfo[0]['url']

# Download the image
img_data = requests.get(image_url).content
with open("temp.jpg", "wb") as f:
    f.write(img_data)

# Post to Mastodon
mastodon = Mastodon(
    access_token=MASTODON_TOKEN,
    api_base_url='https://mastodon.social'
)

media = mastodon.media_post("temp.jpg", sensitive=True)
status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
mastodon.status_post(status=status, media_ids=[media])

print("posted:", status)
