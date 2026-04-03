# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

SteamArt is a Python CLI utility that automates uploading images to Steam Community Artwork. It simulates browser-based uploads using scraped form tokens and TLS fingerprint impersonation via `curl_cffi`.

## Running

```bash
python steam_upload.py <path_to_image> <quantity> [--delay <seconds>] [--reset-cookies]
```

On first run, prompts for cookies and saves them to `~/.config/steamart/cookies.json`. Use `--reset-cookies` to re-enter them.

Dependencies: `curl_cffi` (install via `pip install curl_cffi`).

## Architecture

Single-script design (`steam_upload.py`) with this upload flow:

1. **GET** the Steam edit form to capture dynamic tokens (`wg`, `wg_hmac`, `token`, `cloudfilenameprefix`) and the real upload URL from the `<form action="...">` attribute
2. **POST** multipart form data (image + tokens) via `CurlMime` to the extracted upload URL with Chrome TLS impersonation
3. Check the `Location` redirect header for `fileuploadsuccess=1`

### Key implementation details

- `image_dimensions()` reads PNG/JPEG dimensions from raw file headers (no PIL dependency) — parses PNG IHDR chunk and JPEG SOF markers directly
- `curl_cffi` with `impersonate="chrome"` is required for TLS fingerprint impersonation; standard `requests` gets blocked by Steam
- Upload titles are random 16-character hex strings (`secrets.token_hex(8)`)
- Enforces Steam's 5 MB file size limit before uploading
- Form field order in the multipart POST matches browser form submission order

## Credentials

Authenticates via two Steam cookies: `sessionid` and `steamLoginSecure`. These expire periodically and must be refreshed from an authenticated browser session (DevTools > Application > Cookies > `steamcommunity.com`).
