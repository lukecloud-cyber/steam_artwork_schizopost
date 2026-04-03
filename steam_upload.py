import os
import re
import json
import time
import struct
import argparse
import secrets
from pathlib import Path
from curl_cffi import requests, CurlMime
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status

console = Console()

CONFIG_DIR = Path("~/.config/steamart").expanduser()
COOKIES_FILE = CONFIG_DIR / "cookies.json"


def load_or_prompt_cookies() -> tuple[str, str]:
    """Load saved cookies, or prompt the user to enter them."""
    if COOKIES_FILE.exists():
        data = json.loads(COOKIES_FILE.read_text())
        sid = data.get("sessionid", "")
        lsc = data.get("steamLoginSecure", "")
        if sid and lsc:
            console.print("[dim]Loaded cookies from[/] [cyan]~/.config/steamart/cookies.json[/]")
            return sid, lsc

    console.print()
    console.print(Panel.fit(
        "[bold]This script needs two cookies from your browser.[/]\n"
        "\n"
        "[dim]How to find them:[/]\n"
        "\n"
        "  1. Log into [cyan]steamcommunity.com[/]\n"
        "  2. Press [bold]F12[/] to open Developer Tools\n"
        "  3. Go to [bold]Application[/] tab [dim](click >> if hidden)[/]\n"
        "  4. Expand [bold]Cookies[/] > [cyan]https://steamcommunity.com[/]\n"
        "  5. Copy the values for:\n"
        "     [green]sessionid[/]  and  [green]steamLoginSecure[/]\n"
        "\n"
        f"[dim]Cookies will be saved to {COOKIES_FILE}[/]",
        title="[bold yellow]Steam Cookie Setup[/]",
        border_style="yellow",
        padding=(1, 3),
    ))
    console.print()

    session_id = Prompt.ask("[green]sessionid[/]").strip()
    login_secure = Prompt.ask("[green]steamLoginSecure[/]").strip()

    if not session_id or not login_secure:
        console.print("[bold red]Both cookies are required.[/]")
        raise SystemExit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_FILE.write_text(json.dumps({
        "sessionid": session_id,
        "steamLoginSecure": login_secure,
    }, indent=2) + "\n")
    console.print(f"[green]Cookies saved to[/] [cyan]{COOKIES_FILE}[/]")

    return session_id, login_secure


def clear_cookies():
    """Remove saved cookies so the user is prompted again."""
    if COOKIES_FILE.exists():
        COOKIES_FILE.unlink()
        console.print("[yellow]Saved cookies cleared.[/]")


def extract_field(html: str, name: str) -> str:
    m = re.search(rf'name="{name}"\s+value="([^"]*)"', html)
    return m.group(1) if m else ""


def image_dimensions(path: str) -> tuple[int, int]:
    """Read image width/height from JPEG or PNG headers without PIL."""
    with open(path, "rb") as f:
        header = f.read(24)

    if header[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack(">II", header[16:24])
        return w, h

    if header[:2] == b'\xff\xd8':  # JPEG — scan for SOF marker
        with open(path, "rb") as f:
            data = f.read()
        i = 2
        while i < len(data) - 8:
            if data[i] != 0xff:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + length

    return 0, 0


def upload_image(image_path: str, title: str, session_id: str, login_secure: str) -> bool:
    """Upload a single image as Steam community artwork. Returns True on success."""
    edit_url = "https://steamcommunity.com/sharedfiles/edititem/767/3/"
    mime = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"

    cookies = {
        "sessionid": session_id,
        "steamLoginSecure": login_secure,
    }

    try:
        # Step 1: GET the form to pull dynamic tokens and real upload URL
        form_resp = requests.get(edit_url, cookies=cookies, impersonate="chrome")
        form_html = form_resp.text

        action_match = re.search(r'<form[^>]+action="([^"]+)"', form_html)
        upload_url = action_match.group(1) if action_match else edit_url

        width, height = image_dimensions(image_path)
        file_size = os.path.getsize(image_path)
        if file_size > 5 * 1024 * 1024:
            console.print(f"  [red]File exceeds Steam's 5 MB limit[/] ({file_size / 1024 / 1024:.1f} MB)")
            return False

        # Extract values from form — send as-is (URL-encoded), do NOT unquote
        wg = extract_field(form_html, "wg")
        wg_hmac = extract_field(form_html, "wg_hmac")
        token = extract_field(form_html, "token")

        if not wg or not token:
            console.print("  [red]Failed to extract form tokens — cookies may have expired[/]")
            console.print("  [dim]Run with --reset-cookies to enter new ones[/]")
            return False

        # Extract cloudfilenameprefix from JS if present
        prefix_match = re.search(r"cloudfilenameprefix\.value = '([^']*)'", form_html)
        prefix = prefix_match.group(1) if prefix_match else ""

        # Step 2: POST to the real upload endpoint
        with open(image_path, "rb") as f:
            file_bytes = f.read()

        mp = CurlMime()
        mp.addpart(name="redirect_uri", data=extract_field(form_html, "redirect_uri").encode())
        mp.addpart(name="wg", data=wg.encode())
        mp.addpart(name="wg_hmac", data=wg_hmac.encode())
        mp.addpart(name="realm", data=extract_field(form_html, "realm").encode())
        mp.addpart(name="appid", data=b"767")
        mp.addpart(name="consumer_app_id", data=b"767")
        mp.addpart(name="sessionid", data=session_id.encode())
        mp.addpart(name="token", data=token.encode())
        mp.addpart(name="cloudfilenameprefix", data=prefix.encode())
        mp.addpart(name="publishedfileid", data=b"0")
        mp.addpart(name="id", data=b"0")
        mp.addpart(name="file_type", data=b"3")
        mp.addpart(name="image_width", data=str(width).encode())
        mp.addpart(name="image_height", data=str(height).encode())
        mp.addpart(name="title", data=title.encode())
        mp.addpart(name="file", filename=os.path.basename(image_path),
                   content_type=mime, data=file_bytes)
        mp.addpart(name="description", data=b"")
        mp.addpart(name="visibility", data=b"0")
        mp.addpart(name="agree_terms", data=b"on")

        resp = requests.post(
            upload_url,
            multipart=mp,
            headers={
                "Referer": "https://steamcommunity.com/",
                "Origin": "https://steamcommunity.com",
            },
            allow_redirects=False,
            impersonate="chrome",
        )

        redirect_url = resp.headers.get("location", "")

        if "fileuploadsuccess=1" in redirect_url:
            return True

        result_match = re.search(r"fileuploadsuccess=(\d+)", redirect_url)
        if result_match:
            console.print(f"  [red]Steam returned EResult={result_match.group(1)}[/]")
        else:
            console.print("  [red]Upload failed — unexpected response[/]")

        return False

    except FileNotFoundError:
        console.print(f"  [red]File not found:[/] {image_path}")
        return False
    except Exception as e:
        console.print(f"  [red]Error:[/] {e}")
        return False


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def collect_images(path: str) -> list[str]:
    """Return a list of image file paths from a file or directory."""
    if os.path.isfile(path):
        return [path]

    if os.path.isdir(path):
        images = sorted(
            f.path for f in os.scandir(path)
            if f.is_file() and os.path.splitext(f.name)[1].lower() in IMAGE_EXTENSIONS
        )
        return images

    return []


def main():
    parser = argparse.ArgumentParser(description="Upload images to Steam community artwork.")
    parser.add_argument("path", help="Image file or folder of images to upload")
    parser.add_argument("quantity", type=int, nargs="?", default=1,
                        help="Number of times to upload each image (default: 1)")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between uploads (default: 5)")
    parser.add_argument("--reset-cookies", action="store_true", help="Clear saved cookies and enter new ones")
    args = parser.parse_args()

    if args.reset_cookies:
        clear_cookies()

    images = collect_images(args.path)
    if not images:
        console.print(f"[bold red]No images found:[/] {args.path}")
        return

    total = len(images) * args.quantity
    console.print(
        f"\n[bold]Found [cyan]{len(images)}[/cyan] image(s), "
        f"uploading each [cyan]{args.quantity}[/cyan] time(s) "
        f"[dim]({total} total)[/dim][/bold]\n"
    )

    session_id, login_secure = load_or_prompt_cookies()
    console.print()

    success = 0
    upload_num = 0
    for image_path in images:
        for r in range(args.quantity):
            upload_num += 1
            random_title = secrets.token_hex(8)
            filename = os.path.basename(image_path)
            label = f"[{upload_num}/{total}] {filename}"
            if args.quantity > 1:
                label += f" (round {r + 1}/{args.quantity})"

            with Status(f"[bold cyan]Uploading {filename}...[/]", console=console, spinner="dots"):
                result = upload_image(image_path, random_title, session_id, login_secure)

            if result:
                console.print(f"  [green]OK[/green]  {label}")
                success += 1
            else:
                console.print(f"  [red]FAIL[/red]  {label}")

            if upload_num < total:
                with Status(f"[dim]Waiting {args.delay}s...[/]", console=console, spinner="dots"):
                    time.sleep(args.delay)

    # Summary
    color = "green" if success == total else ("yellow" if success > 0 else "red")
    console.print(f"\n[bold {color}]Done: {success}/{total} uploaded successfully.[/]\n")


if __name__ == "__main__":
    main()
