# Steam Artwork Schizopost

A joke CLI tool for flooding your Steam Community Artwork page with nonsensical repeat uploads. Feed it an image (or a whole folder of them) and it'll spam-upload them to your profile so it looks like unhinged schizoposting artwork.

## Features

- Upload a single image or an entire folder of images
- Repeat uploads with a configurable quantity and delay
- Reads PNG/JPEG dimensions directly from file headers (no Pillow needed)
- Chrome TLS fingerprint impersonation via `curl_cffi` to avoid bot detection
- Interactive first-run cookie setup with persistent storage (`~/.config/steam_artwork_schizopost/cookies.json`)
- Validates file size against Steam's 5 MB limit before uploading

## Installation

### Prerequisites

Install [Git](https://git-scm.com/) if you don't have it:

- **Windows:** `winget install Git.Git` (restart PowerShell after)
- **macOS:** `brew install git`
- **Linux:** `sudo apt install git` or `sudo dnf install git`

You'll also need [Python 3.10+](https://www.python.org/downloads/).

### Clone and install

```bash
git clone https://github.com/lukecloud-cyber/steam_artwork_schizopost.git
cd steam_artwork_schizopost
pip install .
```

## Usage

```bash
# Upload a single image
python steam_artwork_schizopost.py photo.png

# Upload a single image 3 times
python steam_artwork_schizopost.py photo.png 3

# Upload every image in a folder
python steam_artwork_schizopost.py ./artwork/

# Upload every image in a folder 2 times each
python steam_artwork_schizopost.py ./artwork/ 2

# Use a custom Steam request timeout
python steam_artwork_schizopost.py ./artwork/ 2 --timeout 45.5

# If installed via pip, you can also use the console script
steam_artwork_schizopost ./artwork/ 2
```

```bash
usage: steam_artwork_schizopost.py [-h] [--delay DELAY] [--timeout TIMEOUT] [--reset-cookies] path [quantity]

positional arguments:
  path               Image file or folder of images to upload
  quantity           Number of times to upload each image (default: 1)

options:
  --delay DELAY      Seconds between uploads (default: 5)
  --timeout TIMEOUT  Seconds to wait for Steam requests (default: 30)
  --reset-cookies    Clear saved cookies and enter new ones
```

On first run, the tool will prompt you to enter two cookies from your browser:

1. Log into [steamcommunity.com](https://steamcommunity.com)
2. Open DevTools (F12) > Application > Cookies > `https://steamcommunity.com`
3. Copy the values for **sessionid** and **steamLoginSecure**

Cookies are saved to `~/.config/steam_artwork_schizopost/cookies.json` and reused on subsequent runs. Use `--reset-cookies` if they expire.

Only `.png`, `.jpg`, and `.jpeg` inputs are accepted. If the saved cookie file becomes corrupted, the tool will prompt you to enter fresh values again.

Be careful with local debugging artifacts: raw request dumps can contain sensitive Steam session data and should not be kept around unredacted.

## How It Works

1. **GET** Steam's artwork edit form to extract dynamic tokens (`wg`, `wg_hmac`, `token`, `cloudfilenameprefix`) and the upload URL
2. **POST** the image as multipart form data with all required tokens
3. Check the redirect header for `fileuploadsuccess=1` to confirm success

Each upload uses a random hex string as the artwork title for maximum incoherence.

## Requirements

- Python 3.10+
- `curl_cffi` and `rich` (installed automatically via `pip install .`)

## License

MIT
