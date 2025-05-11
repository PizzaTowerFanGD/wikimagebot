import requests
from mastodon import Mastodon
from PIL import Image
import os

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')

# proper user-agent per wikipedia policy
HEADERS = {
    "User-Agent": "wikimagebot.mastodon.social/1.0 (https://github.com/PizzaTowerFanGD/wikimagebot; sprusebenaustinalt@gmail.com)"
}

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
                "iiprop": "url",
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
            image_url = imageinfo[0]['url']
            if image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                break
            else:
                print(f"Invalid file type: {image_url}. Retrying...")
        else:
            print("No image info found. Retrying...")
    except Exception as e:
        print(f"Error fetching image: {e}. Retrying...")

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
            print(f"Converting {img.format} to JPEG...")
            img = img.convert("RGB")
            temp_file = "temp.jpg"
            img.save(temp_file, "JPEG")
        else:
            os.rename(temp_file, "temp.jpg")
            temp_file = "temp.jpg"

except Exception as e:
    print(f"Error processing image: {e}")
    exit(1)

# post to mastodon
mastodon = Mastodon(
    access_token=MASTODON_TOKEN,
    api_base_url='https://mastodon.social'
)

media = mastodon.media_post(temp_file)
status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
mastodon.status_post(status=status, media_ids=[media], sensitive=True)

print("posted:", status)
