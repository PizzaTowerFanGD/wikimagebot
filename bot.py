print("booting up", flush=True) # so theres this weird bug where sometimes python doesnt output anything and just freezes. this is a test.

import requests
from mastodon import Mastodon
from PIL import Image
import os
from google import genai
import time

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
MANUAL_RUN = os.getenv('MANUAL_RUN', 'false').lower() == 'true'
# Initial backoff for Wikipedia API request
wiki_bypassratelimit = 1

HEADERS = {
    "User-Agent": "wikimagebot.mastodon.social/1.0 (https://github.com/PizzaTowerFanGD/wikimagebot)"
}

client = genai.Client()

# --- Wikipedia Image Fetching Loop with Backoff ---
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
        print(data)

        page = next(iter(data['query']['pages'].values()))
        title = page['title']
        imageinfo = page.get('imageinfo', [])

        if imageinfo:
            # Sort by size, take the largest (or just the first valid one)
            imageinfo = sorted(imageinfo, key=lambda x: x.get('width', 0), reverse=True)
            info = imageinfo[0]
            image_url = info['url']

            # Check file extension explicitly, although we check format later
            if image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                print(f"Found image URL: {image_url}")
                # Reset backoff for the next API call if successful
                wiki_bypassratelimit = 1
                break
            else:
                print(f"Invalid file type from URL ending: {image_url}. Retrying after {wiki_bypassratelimit} seconds...")
                time.sleep(wiki_bypassratelimit)
                wiki_bypassratelimit = wiki_bypassratelimit * 1.5  # Exponential backoff for Wikipedia

        else:
            print("No image info found. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit = wiki_bypassratelimit * 1.5

    except requests.exceptions.HTTPError as e:
        # Use res variable safely only if defined
        status_code = getattr(res, "status_code", None)
        if status_code == 429:
            print(f"Wikipedia Rate Limited (429). Backing off for {wiki_bypassratelimit} seconds...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit = wiki_bypassratelimit * 2  # Increase backoff significantly for rate limits
        else:
            print(f"HTTP error fetching image: {e}. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit = wiki_bypassratelimit * 1.5

    except Exception as e:
        print(f"Error fetching image: {e}. Retrying...")
        time.sleep(wiki_bypassratelimit)
        wiki_bypassratelimit = wiki_bypassratelimit * 1.5


# --- Image Downloading and Processing with Backoff ---
file_extension = os.path.splitext(image_url)[1] or ".jpg"
temp_file = f"temp_image{file_extension}"
download_success = False
download_bypassratelimit = 1

while not download_success:
    try:
        print(f"Attempting to download image from: {image_url}")
        response = requests.get(image_url, stream=True, headers=HEADERS)
        response.raise_for_status()

        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(1024):
                if not chunk:
                    continue
                f.write(chunk)

        print("Image downloaded successfully.")
        download_success = True
        # Reset download backoff if successful
        download_bypassratelimit = 1

    except requests.exceptions.HTTPError as e:
        status_code = getattr(response, "status_code", None)
        if status_code == 429:
            print(f"Server returned 429 Rate Limit while downloading. Backing off for {download_bypassratelimit} seconds...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit = download_bypassratelimit * 2
        else:
            print(f"HTTP error downloading image ({status_code}): {e}. Retrying...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit = download_bypassratelimit * 1.5

    except Exception as e:
        print(f"Error during initial download: {e}. Retrying...")
        time.sleep(download_bypassratelimit)
        download_bypassratelimit = download_bypassratelimit * 1.5

    # Safety break for download loop to prevent infinite loops if the URL is permanently bad
    if download_bypassratelimit > 300:  # Stop trying after 5 minutes of backoff (arbitrary limit)
        print("Max download retries reached. Exiting.")
        exit(1)


# --- Image Format Conversion ---
try:
    with Image.open(temp_file) as img:
        output_filename = "temp.jpg"
        if img.format and img.format.upper() != "JPEG":
            print(f"Converting {img.format} to jpeg...")
            img = img.convert("RGB")
            img.save(output_filename, "JPEG")
        else:
            # If it was already a compatible format (or we couldn't determine format clearly)
            os.replace(temp_file, output_filename)

        temp_file = output_filename

except Exception as e:
    print(f"Error processing or converting image: {e}")
    # Clean up potentially partially downloaded file if conversion fails
    if os.path.exists(temp_file):
        os.remove(temp_file)
    exit(1)


# --- Gemini Alt Text Generation ---
try:
    with open(temp_file, "rb") as f:
        image = Image.open(f)
        # Note: depending on the genai SDK version, you may need to pass bytes or a different object.
        # Keep this call as-is and adapt if your SDK expects a different payload.
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[image, "You are generating alt text for a mastodon bot that posts random Wikipedia images. Respond with only up to 2 concise English sentences describing the image for accessibility."]
        )
    # Some SDK responses provide .text or .output; guard both
    description = getattr(response, "text", None) or getattr(response, "output", None) or ""
    description = description.strip() or "no description available, it's blank"
except Exception as e:
    print(f"Gemini alt generation failed: {e}")
    description = f"no description available, error: {e}"


# --- Posting to Mastodon ---
try:
    mastodon = Mastodon(
        access_token=MASTODON_TOKEN,
        api_base_url='https://mastodon.social'
    )

    # mastodon.media_post returns a dict; extract id if so
    media_obj = mastodon.media_post(temp_file, description=description)
    media_id = media_obj.get("id") if isinstance(media_obj, dict) else media_obj

    if MANUAL_RUN:
        status = f'Manually Triggered: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
    else:
        status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'

    # Set sensitive=True for random content
    mastodon.status_post(status=status, media_ids=[media_id], sensitive=True)
    print("posted:", status)

finally:
    # Clean up the final temporary image file
    if os.path.exists(temp_file):
        os.remove(temp_file)
