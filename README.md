# wiki-image-bot

Posts random images from Wikipedia to Mastodon.

## How to Run Your Own Instance

1. **Fork the Repository:** Click the 'Fork' button at the top right of this page to create your own copy.
2. **Clone and Install Dependencies:**
   Clone your forked repository to your local machine. Make sure to replace `YOUR_USERNAME` with your actual GitHub username in the command below:
   ```bash
   git clone https://github.com/YOUR_USERNAME/wiki-image-bot.git
   cd wiki-image-bot
   pip install -r requirements.txt
   ```
3. **Configure Mastodon Access Token:**
   This bot posts images to Mastodon and requires an access token.
   - Navigate to your Mastodon instance's preferences, then go to 'Development'.
   - Create a new application. Name it something like 'WikiImageBot'.
   - Ensure the application has 'write:media' and 'write:statuses' permissions.
   - After creating the application, your access token will be displayed.
   - Set this token as an environment variable named `MASTODON_TOKEN`. You can do this by:
     - Running `export MASTODON_TOKEN='YOUR_ACCESS_TOKEN'` in your terminal session before running the bot. (Replace `YOUR_ACCESS_TOKEN` with the actual token).
     - Adding this export line to your shell's configuration file (e.g., `~/.bashrc` or `~/.zshrc`) for persistence across sessions.
     - Using a `.env` file in the project root (note: this repository doesn't include built-in support for loading `.env` files, you'd need to add that functionality if desired).
4. **Run the Bot Manually:**
   With dependencies installed and the `MASTODON_TOKEN` environment variable set, run the bot using:
   ```bash
   python bot.py
   ```
5. **Optional: Automated Execution with GitHub Actions:**
   This repository includes a GitHub Actions workflow (`.github/workflows/bot.yml`) to run the bot automatically on a schedule. To enable this in your fork:
   - Go to your forked repository's 'Settings' tab.
   - Navigate to 'Secrets and variables' > 'Actions' in the sidebar.
   - Under 'Repository secrets', click 'New repository secret'.
   - For 'Name', enter `MASTODON_TOKEN`.
   - For 'Secret', paste your Mastodon access token.
   - Click 'Add secret'.
   The GitHub Action should now run as scheduled (e.g., daily) or can be triggered manually from your repository's 'Actions' tab.
