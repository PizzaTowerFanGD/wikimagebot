import requests
from mastodon import Mastodon
from PIL import Image
import os

MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')

while True:
    # Fetch a random Wikipedia image
# Define the user-agent
    headers = {"User-Agent": "wikimagebot/1.0 (https://github.com/PizzaTowerFanGD/wikimagebot)"}

# Example usage in the first request
    res = requests.get("https://en.wikipedia.org/w/api.php", 
                   params={
                       "action": "query",
                       "generator": "random",
                       "grnnamespace": 6,  # Namespace 6 corresponds to files (including images)
                       "prop": "imageinfo",
                       "iiprop": "url",
                       "format": "json"
                   },
                   headers=headers)  # Add headers here
    res.raise_for_status()
    data = res.json()

    # Get the random image and its URL
    page = next(iter(data['query']['pages'].values()))
    title = page['title']
    imageinfo = page.get('imageinfo', [])

    # Check if the imageinfo exists and the file type is valid
    if imageinfo:
        image_url = imageinfo[0]['url']
        if image_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
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
file_extension = os.path.splitext(image_url)[1]  # Get the file extension from the URL
if not file_extension:
    file_extension = ".jpg"  # Default to .jpg if no extension is found

temp_file = f"temp_image{file_extension}"
try:
    response = requests.get(image_url, stream=True)
    response.raise_for_status()
    with open(temp_file, "wb") as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)

    # Validate the downloaded file before processing
    with Image.open(temp_file) as img:
        original_format = img.format
        if original_format.upper() != "JPEG":
            print(f"Converting {original_format} to JPEG...")
            img = img.convert("RGB")  # Convert to RGB for JPEG compatibility
            temp_file = "temp.jpg"
            img.save(temp_file, "JPEG")
        else:
            # Rename to .jpg if it's already JPEG
            os.rename(temp_file, "temp.jpg")
            temp_file = "temp.jpg"
except Exception as e:
    print(f"Error processing image: {e}")
    exit(1)

# Post to Mastodon
mastodon = Mastodon(
    access_token=MASTODON_TOKEN,
    api_base_url='https://mastodon.social'
)

media = mastodon.media_post(temp_file)
status = f'Random Wikipedia Image: "{title}"\n{image_url} (BOT POST, MAY CONTAIN BAD CONTENT)'
mastodon.status_post(status=status, media_ids=[media], sensitive=True)

print("posted:", status)
