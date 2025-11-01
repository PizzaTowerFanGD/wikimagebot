import requests
from mastodon import Mastodon
from PIL import Image
import os
from google import genai
import time
import sys

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
MANUAL_RUN = os.getenv('MANUAL_RUN', 'false').lower() == 'true'
HEADERS = {
    "User-Agent": "wikimagebot.mastodon.social/1.0 (https://github.com/PizzaTowerFanGD/wikimagebot)"
}

client = genai.Client()

# --- Wikipedia Image Fetching Loop with Backoff ---
wiki_bypassratelimit = 1
image_url = None
title = None

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
            headers=HEADERS,
            timeout=30
        )
        res.raise_for_status()
        data = res.json()
        # Defensive checks
        if 'query' not in data or 'pages' not in data['query']:
            print("No pages returned, retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 1.5
            continue

        page = next(iter(data['query']['pages'].values()))
        title = page.get('title', 'untitled')
        imageinfo = page.get('imageinfo', [])

        if imageinfo:
            imageinfo = sorted(imageinfo, key=lambda x: x.get('width', 0), reverse=True)
            info = imageinfo[0]
            image_url = info.get('url')
            if image_url and image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                print(f"Found image URL: {image_url}")
                wiki_bypassratelimit = 1
                break
            else:
                print(f"Invalid or missing image URL: {image_url}. Backing off {wiki_bypassratelimit}s...")
                time.sleep(wiki_bypassratelimit)
                wiki_bypassratelimit *= 1.5
        else:
            print("No image info found. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 1.5

    except requests.exceptions.HTTPError as e:
        status = getattr(res, "status_code", None)
        if status == 429:
            print(f"Wikipedia Rate Limited (429). Backing off for {wiki_bypassratelimit} seconds...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 2
        else:
            print(f"HTTP error fetching image: {e}. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 1.5
    except Exception as e:
        print(f"Error fetching image: {e}. Retrying...")
        time.sleep(wiki_bypassratelimit)
        wiki_bypassratelimit *= 1.5

# --- Image Downloading and Processing with Backoff ---
if not image_url:
    print("No image URL found; exiting.")
    sys.exit(1)

file_extension = os.path.splitext(image_url)[1] or ".jpg"
temp_file = f"temp_image{file_extension}"
download_success = False
download_bypassratelimit = 1

while not download_success:
    try:
        print(f"Attempting to download image from: {image_url}")
        response = requests.get(image_url, stream=True, headers=HEADERS, timeout=60)
        response.raise_for_status()

        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(1024):
                if chunk:
                    f.write(chunk)

        print("Image downloaded successfully.")
        download_success = True
        download_bypassratelimit = 1

    except requests.exceptions.HTTPError as e:
        status = getattr(response, "status_code", None)
        if status == 429:
            print(f"Server returned 429 Rate Limit while downloading. Backing off for {download_bypassratelimit} seconds...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit *= 2
        else:
            print(f"HTTP error downloading image ({status}): {e}. Retrying...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit *= 1.5
    except Exception as e:
        print(f"Error during download: {e}. Retrying...")
        time.sleep(download_bypassratelimit)
        download_bypassratelimit *= 1.5

    if download_bypassratelimit > 300:
        print("Max download retries reached. Exiting.")
        sys.exit(1)

# --- Image Format Conversion ---
try:
    with Image.open(temp_file) as img:
        output_filename = "temp.jpg"
        if img.format and img.format.upper() != "JPEG":
            print(f"Converting {img.format} to JPEG...")
            rgb = img.convert("RGB")
            rgb.save(output_filename, "JPEG")
        else:
            # If it's already JPEG-compatible, rename
            os.replace(temp_file, output_filename)
        temp_file = output_filename
except Exception as e:
    print(f"Error processing or converting image: {e}")
    if os.path.exists(temp_file):
        os.remove(temp_file)
    sys.exit(1)

# --- Generate alt text and post to Mastodon ---
description = "no description available, its blank"
mastodon = None
media_id = None

try:
    # Generate alt text (ensure string is closed properly)
    with open(temp_file, "rb") as f:
        # Many model APIs expect bytes or base64; adjust as required by genai client.
        # Here we pass a textual prompt plus (optionally) mention the file name.
        img=Image.open(temp_file)
        prompt = (
            "You are generating alt text for a Mastodon bot that posts random "
            "Wikipedia images. Respond with only up to 2 concise English sentences "
            "describing the image for accessibility."
        )
        # Adapt this call to the actual genai client signature your environment requires.
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[img,prompt]
        )

    # Access text (confirm correct attribute for your genai client)
    description = getattr(response, "text", None) or getattr(response, "output_text", None) or str(response)
    description = description.strip() or description

    # Post to Mastodon
    mastodon = Mastodon(
        access_token=MASTODON_TOKEN,
        api_base_url='https://mastodon.social'
    )

    media = mastodon.media_post(temp_file, description=description)
    # media_post may return media dict or id; try to extract id
    if isinstance(media, dict) and "id" in media:
        media_id = media["id"]
    else:
        # assume it's a raw id or object with id attribute
        media_id = getattr(media, "id", media)

    if MANUAL_RUN:
        status = f'Manually Triggered: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
    else:
        status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'

    # Post status. mastodon.status_post expects a list of media IDs (integers)
    mastodon.status_post(status=status, media_ids=[media_id], sensitive=True)
    print("posted:", status)

except Exception as e:
    print(f"Error generating alt text or posting: {e}")
    # do not sys.exit here if you want to retry later; for now, exit with error
    sys.exit(1)

finally:
    # Clean up the final temporary image file if it still exists
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except Exception as cleanup_err:
        print(f"Error cleaning up temp file: {cleanup_err}")
