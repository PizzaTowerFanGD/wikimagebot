print("booting up", flush=True)

import requests
from mastodon import Mastodon
from PIL import Image
import os
from google import genai
from google.genai import types
import time

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
MANUAL_RUN = os.getenv('MANUAL_RUN', 'false').lower() == 'true'

wiki_bypassratelimit = 1
HEADERS = {
    "User-Agent": f"wikimagebot.mastodon.social/1.0 (https://github.com/PizzaTowerFanGD/wikimagebot, contact me: sprusebenaustinalt@gmail.com, testing: {os.getenv('MANUAL_RUN')}"
}

client = genai.Client()
WIKIBASE = "https://en.wikipedia.org"

# --- Wikipedia Image Fetching Loop ---
while True:
    try:
        res = requests.get(
            f"{WIKIBASE}/w/api.php",
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
            imageinfo = sorted(imageinfo, key=lambda x: x.get('width', 0), reverse=True)
            info = imageinfo[0]
            image_url = info['url']

            if image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
                print(f"Found image URL: {image_url}")
                wiki_bypassratelimit = 1
                break
            else:
                print(f"Invalid file type: {image_url}. Retrying in {wiki_bypassratelimit}s...")
                time.sleep(wiki_bypassratelimit)
                wiki_bypassratelimit *= 1.5
        else:
            print("No image info found. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 1.5

    except requests.exceptions.HTTPError as e:
        status_code = getattr(res, "status_code", None)
        if status_code == 429:
            print(f"Rate Limited (429). Backing off {wiki_bypassratelimit}s...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 2
        else:
            print(f"HTTP error: {e}. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit *= 1.5
    except Exception as e:
        print(f"Error fetching image: {e}. Retrying...")
        time.sleep(wiki_bypassratelimit)
        wiki_bypassratelimit *= 1.5

# --- Image Download ---
file_extension = os.path.splitext(image_url)[1] or ".jpg"
temp_file = f"temp_image{file_extension}"
download_success = False
download_bypassratelimit = 1

while not download_success:
    try:
        print(f"Downloading image: {image_url}")
        response = requests.get(image_url, stream=True, headers=HEADERS)
        response.raise_for_status()
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(1024):
                if chunk:
                    f.write(chunk)
        print("Image downloaded successfully.")
        download_success = True
        download_bypassratelimit = 1
    except requests.exceptions.HTTPError as e:
        status_code = getattr(response, "status_code", None)
        if status_code == 429:
            print(f"429 Rate Limit. Backing off {download_bypassratelimit}s...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit *= 2
        else:
            print(f"HTTP error downloading image ({status_code}): {e}. Retrying...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit *= 1.5
    except Exception as e:
        print(f"Download error: {e}. Retrying...")
        time.sleep(download_bypassratelimit)
        download_bypassratelimit *= 1.5
    if download_bypassratelimit > 300:
        print("Max download retries reached. Exiting.")
        exit(1)

# --- Image Conversion ---
try:
    with Image.open(temp_file) as img:
        output_filename = "temp.jpg"
        if img.format and img.format.upper() != "JPEG":
            print(f"Converting {img.format} to JPEG...")
            img = img.convert("RGB")
            img.save(output_filename, "JPEG")
        else:
            os.replace(temp_file, output_filename)
        temp_file = output_filename
except Exception as e:
    print(f"Image processing error: {e}")
    if os.path.exists(temp_file):
        os.remove(temp_file)
    exit(1)

# --- Gemini Alt Text Generation ---
try:
    with open(temp_file, "rb") as f:
        image = Image.open(f)
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[image, "You are generating alt text for a mastodon bot that posts random Wikipedia images. Respond with only up to 2 concise English sentences describing the image for accessibility."]
        )
    description = getattr(response, "text", None) or getattr(response, "output", None) or ""
    description = description.strip() or "no description available"
except Exception as e:
    print(f"Gemini alt generation failed: {e}")
    description = f"no description available, error: {e}"

# --- Context Generation with Search Grounding ---
try:
    grounding_tool = types.Tool(
        google_search=types.GoogleSearch()
    )
    config = types.GenerateContentConfig(
        tools=[grounding_tool]
    )

    context_prompt = f"""
Alt text: {description}
Title: {title}
Provide 1-2 concise sentences giving extra context or background about this image, using verifiable information.
Respond in clear English.
"""
    context_response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=context_prompt,
        config=config
    )
    context_text = getattr(context_response, "text", None) or getattr(context_response, "output", None) or ""
    context_text = context_text.strip() or "no context available"
except Exception as e:
    print(f"Context generation failed: {e}")
    context_text = "no context available"

# --- Posting to Mastodon ---
try:
    mastodon = Mastodon(
        access_token=MASTODON_TOKEN,
        api_base_url='https://mastodon.social'
    )
    media_obj = mastodon.media_post(temp_file, description=description)
    media_id = media_obj.get("id") if isinstance(media_obj, dict) else media_obj

    if MANUAL_RUN:
        status = f'Manually Triggered: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
    else:
        status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'

    main_status = mastodon.status_post(status=status, media_ids=[media_id], sensitive=True)
    print("posted:", status)

    # --- Always Post Context Reply ---
    mastodon.status_post(
        status=context_text,
        in_reply_to_id=main_status["id"]
    )
    print("posted context reply:", context_text)

finally:
    if os.path.exists(temp_file):
        os.remove(temp_file)
