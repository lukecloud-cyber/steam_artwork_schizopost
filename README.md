# Steam Artwork Uploader

A CLI tool that uploads images to Steam Community Artwork, bypassing the manual web interface. It authenticates using your browser session cookies, scrapes Steam's upload form for dynamic tokens, and submits artwork via multipart POST with TLS fingerprint impersonation.

## Features

- Uploads a single image multiple times with configurable delay
- Reads PNG/JPEG dimensions directly from file headers (no Pillow needed)
- Chrome TLS fingerprint impersonation via `curl_cffi` to avoid bot detection
- Interactive first-run cookie setup with persistent storage (`~/.config/steamart/cookies.json`)
- Validates file size against Steam's 5 MB limit before uploading

## Installation

```bash
git clone https://github.com/lukecloud-cyber/steam_artwork_uploader.git
cd steam_artwork_uploader
pip install .
```

## Usage

```bash
# After installing
steamart photo.png 3

# Or run directly
python steam_upload.py photo.png 3
```

```
usage: steam_upload.py [-h] [--delay DELAY] [--reset-cookies] image quantity

positional arguments:
  image              Image file to upload (PNG or JPEG)
  quantity           Number of times to upload it

options:
  --delay DELAY      Seconds between uploads (default: 5)
  --reset-cookies    Clear saved cookies and enter new ones
```

On first run, the tool will prompt you to enter two cookies from your browser:

1. Log into [steamcommunity.com](https://steamcommunity.com)
2. Open DevTools (F12) → Application → Cookies → `https://steamcommunity.com`
3. Copy the values for **sessionid** and **steamLoginSecure**

Cookies are saved to `~/.config/steamart/cookies.json` and reused on subsequent runs. Use `--reset-cookies` if they expire.

## How It Works

1. **GET** Steam's artwork edit form to extract dynamic tokens (`wg`, `wg_hmac`, `token`, `cloudfilenameprefix`) and the upload URL
2. **POST** the image as multipart form data with all required tokens
3. Check the redirect header for `fileuploadsuccess=1` to confirm success

Each upload uses a random hex string as the artwork title.

## Requirements

- Python 3.10+
- `curl_cffi` (installed automatically via `pip install .`)

## License

MIT
