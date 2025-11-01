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
                wiki_bypassratelimit = wiki_bypassratelimit * 1.5 # Exponential backoff for Wikipedia
                
        else:
            print("No image info found. Retrying...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit = wiki_bypassratelimit * 1.5

    except requests.exceptions.HTTPError as e:
        if res.status_code == 429:
            print(f"Wikipedia Rate Limited (429). Backing off for {wiki_bypassratelimit} seconds...")
            time.sleep(wiki_bypassratelimit)
            wiki_bypassratelimit = wiki_bypassratelimit * 2 # Increase backoff significantly for rate limits
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
                f.write(chunk)
        
        print("Image downloaded successfully.")
        download_success = True
        # Reset download backoff if successful
        download_bypassratelimit = 1

    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:
            print(f"Server returned 429 Rate Limit while downloading. Backing off for {download_bypassratelimit} seconds...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit = download_bypassratelimit * 2
        else:
            print(f"HTTP error downloading image ({response.status_code}): {e}. Retrying...")
            time.sleep(download_bypassratelimit)
            download_bypassratelimit = download_bypassratelimit * 1.5
            
    except Exception as e:
        print(f"Error during initial download: {e}. Retrying...")
        time.sleep(download_bypassratelimit)
        download_bypassratelimit = download_bypassratelimit * 1.5

    # Safety break for download loop to prevent infinite loops if the URL is permanently bad
    if download_bypassratelimit > 300: # Stop trying after 5 minutes of backoff (arbitrary limit)
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
            os.rename(temp_file, output_filename)
        
        temp_file = output_filename

except Exception as e:
    print(f"Error processing or converting image: {e}")
    # Clean up potentially partially downloaded file if conversion fails
    if os.path.exists(temp_file):
        os.remove(temp_file)
    exit(1)

# --- Gemini Alt Text Generation (No backoff implemented here as Gemini usually handles its own retries/limits internally) ---
try:
    image = Image.open(temp_file)
    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=[image, f"you are generating alt text for a mastodon bot that posts random wikipedia images. respond with only up to 2 concise english sentences describing the image for accessibility. do not include quotes, punctuation beyond normal grammar, introductions, explanations, or formatting. however, if there is text, you must include a transcript, and an english translation if not in english. — output only the alt text itself. the image itself has a file name of {title}, for context."]
    )
    description = response.text.strip() or "no description available, its blank"
except Exception as e:
    print(f"Gemini alt generation failed: {e}")
    description = f"no description available, error: {e}"

# --- Posting to Mastodon ---
try:
    mastodon = Mastodon(
        access_token=MASTODON_TOKEN,
        api_base_url='https://mastodon.social'
    )

    media = mastodon.media_post(temp_file, description=description)

    if MANUAL_RUN:
        status = f'Manually Triggered: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
    else:
        status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'

    # Set sensitive=False if you trust the content, or keep True for maximum safety on random fetches
    mastodon.status_post(status=status, media_ids=[media], sensitive=True)
    print("posted:", status)

finally:
    # Clean up the final temporary image file
    if os.path.exists(temp_file):
        os.remove(temp_file)    
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
        contents=[image, f"you are generating alt text for a mastodon bot that posts random wikipedia images. respond with only up to 2 concise english sentences describing the image for accessibility. do not include quotes, punctuation beyond normal grammar, introductions, explanations, or formatting. however, if there is text, you must include a transcript, and an english translation if not in english. — output only the alt text itself. the image itself has a file name of {title}, for context."]
    )
    description = response.text.strip() or "no description available, its blank"
except Exception as e:
    print(f"gemini alt generation failed: {e}")
    description = f"no description available, error: {e}"

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
 
