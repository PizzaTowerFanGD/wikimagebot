import requests
from mastodon import Mastodon
import os

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')

res = requests.get("https://en.wikipedia.org/w/api.php", params={{
    "action": "query",
    "generator": "random",
    "grnnamespace": 0,
    "prop": "images",
    "format": "json"
}})
res.raise_for_status()
data = res.json()

page = next(iter(data['query']['pages'].values()))
title = page['title']
images = page.get('images', [])
image_title = next((img['title'] for img in images if img['title'].lower().endswith(('.jpg', '.jpeg', '.png'))), None)

if not image_title:
    print("no suitable image found")
    exit(0)

image_info = requests.get("https://en.wikipedia.org/w/api.php", params={{
    "action": "query",
    "titles": image_title,
    "prop": "imageinfo",
    "iiprop": "url",
    "format": "json"
}}).json()

image_url = next(iter(image_info['query']['pages'].values()))['imageinfo'][0]['url']

img_data = requests.get(image_url).content
with open("temp.jpg", "wb") as f:
    f.write(img_data)

mastodon = Mastodon(
    access_token=MASTODON_TOKEN,
    api_base_url='https://botsin.space'
)

media = mastodon.media_post("temp.jpg")
status = f'"{title}"\n{image_url}'
mastodon.status_post(status=status, media_ids=[media])

print("posted:", status)
