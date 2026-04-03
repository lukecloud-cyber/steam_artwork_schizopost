# SteamArt

A specialized Python utility for automating the upload of images to Steam Community Artwork. This tool is designed to bypass manual upload limitations and includes a specific "long image" fix to ensure images are displayed correctly in Steam profiles.

## Project Overview

- **Purpose:** Automates the process of uploading a single image to Steam multiple times.
- **Key Feature:** Implements the "long image" fix by overriding `image_width` to 1000 and `image_height` to 1 during upload.
- **Technologies:** Python 3, `requests`, `urllib3`.

## Getting Started

### Prerequisites

- **Python 3.x**
- **Requests Library:** Install via pip:
  ```bash
  pip install requests
  ```

### Configuration

The script currently uses hardcoded session credentials (`SESSION_ID` and `LOGIN_SECURE`) within `steam_upload_hardcoded.py`. 

> [!WARNING]
> **Security Risk:** Hardcoded credentials are used for authentication. Avoid sharing this script or committing it to public repositories without removing sensitive information.

### Running the Script

To upload an image multiple times:

```bash
python steam_upload_hardcoded.py <path_to_image> <quantity> [--delay <seconds>]
```

- `<path_to_image>`: Path to the JPG or PNG file.
- `<quantity>`: Number of times to upload the image.
- `--delay`: (Optional) Seconds to wait between uploads (default: 5.0).

## Implementation Details

- **Custom Image Headers:** Includes a native `image_dimensions` function to extract width and height from PNG and JPEG files without requiring heavy dependencies like `PIL` (Pillow).
- **Steam Protocol:** Simulates a browser-based upload by first performing a GET request to capture form tokens (`wg`, `wg_hmac`, `token`) followed by a multipart/form-data POST request.
- **Validation:** Enforces Steam's 5 MB file size limit before attempting an upload.
- **Logging:** Uses Python's `logging` module to provide real-time feedback on upload status and errors.
