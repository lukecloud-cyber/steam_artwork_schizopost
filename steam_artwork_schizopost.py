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

CONFIG_DIR = Path("~/.config/steam_artwork_schizopost").expanduser()
COOKIES_FILE = CONFIG_DIR / "cookies.json"
EDIT_URL = "https://steamcommunity.com/sharedfiles/edititem/767/3/"
DEFAULT_REQUEST_TIMEOUT = 30.0
MAX_FILE_SIZE = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def positive_int(value: str) -> int:
    """argparse type: integer >= 1."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be an integer >= 1")
    return parsed


def positive_float(value: str) -> float:
    """argparse type: float > 0."""
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a number > 0")
    return parsed


def non_negative_float(value: str) -> float:
    """argparse type: float >= 0."""
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a number >= 0")
    return parsed


def is_supported_image(path: Path) -> bool:
    """Return True if the path has a supported image extension."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def detect_mime_type(path: Path) -> str | None:
    """Return MIME type for a supported image, else None."""
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return None


def load_or_prompt_cookies() -> tuple[str, str]:
    """Load saved cookies, or prompt the user to enter them."""
    if COOKIES_FILE.exists():
        try:
            data = json.loads(COOKIES_FILE.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            console.print(f"[yellow]Saved cookies could not be read:[/] {exc}")
            console.print("[dim]You'll be prompted to enter new cookies.[/]")
        else:
            if not isinstance(data, dict):
                console.print("[yellow]Saved cookies are malformed and will be replaced.[/]")
            else:
                sid = data.get("sessionid", "")
                lsc = data.get("steamLoginSecure", "")
                if sid and lsc:
                    console.print("[dim]Loaded cookies from[/] [cyan]~/.config/steam_artwork_schizopost/cookies.json[/]")
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
    try:
        COOKIES_FILE.chmod(0o600)
    except OSError:
        pass
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


def extract_upload_url(html: str) -> str:
    """Extract the upload form action URL."""
    action_match = re.search(r'<form[^>]+action="([^"]+)"', html)
    return action_match.group(1) if action_match else EDIT_URL


def validate_form_response(response, html: str) -> bool:
    """Check that the edit form response looks usable."""
    if response.status_code != 200:
        console.print(f"  [red]Failed to load upload form (HTTP {response.status_code})[/]")
        return False
    if "<form" not in html:
        console.print("  [red]Steam returned an unexpected page instead of the upload form[/]")
        return False
    return True


def extract_form_state(html: str) -> dict[str, str] | None:
    """Extract upload URL and dynamic form fields from the Steam form."""
    wg = extract_field(html, "wg")
    token = extract_field(html, "token")
    if not wg or not token:
        console.print("  [red]Failed to extract form tokens — cookies may have expired[/]")
        console.print("  [dim]Run with --reset-cookies to enter new ones[/]")
        return None

    prefix_match = re.search(r"cloudfilenameprefix\.value = '([^']*)'", html)
    prefix = prefix_match.group(1) if prefix_match else ""

    return {
        "upload_url": extract_upload_url(html),
        "redirect_uri": extract_field(html, "redirect_uri"),
        "wg": wg,
        "wg_hmac": extract_field(html, "wg_hmac"),
        "realm": extract_field(html, "realm"),
        "token": token,
        "cloudfilenameprefix": prefix,
    }


def image_dimensions(path: Path) -> tuple[int, int]:
    """Read image width/height from JPEG or PNG headers without PIL."""
    with path.open("rb") as f:
        header = f.read(24)

    if header[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack(">II", header[16:24])
        return w, h

    if header[:2] == b'\xff\xd8':  # JPEG — scan for SOF marker
        with path.open("rb") as f:
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


def validate_image_file(image_path: Path) -> tuple[str, int, int] | None:
    """Validate local image constraints and return upload metadata."""
    mime = detect_mime_type(image_path)
    if not mime:
        console.print(f"  [red]Unsupported image type:[/] {image_path.name}")
        return None

    file_size = image_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        console.print(f"  [red]File exceeds Steam's 5 MB limit[/] ({file_size / 1024 / 1024:.1f} MB)")
        return None

    width, height = image_dimensions(image_path)
    if width <= 0 or height <= 0:
        console.print(f"  [red]Could not determine image dimensions:[/] {image_path.name}")
        return None

    return mime, width, height


def fetch_form_state(cookies: dict[str, str], request_timeout: float) -> dict[str, str] | None:
    """Fetch the Steam form and extract all upload fields."""
    form_resp = requests.get(
        EDIT_URL,
        cookies=cookies,
        impersonate="chrome",
        timeout=request_timeout,
    )
    form_html = form_resp.text
    if not validate_form_response(form_resp, form_html):
        return None
    return extract_form_state(form_html)


def build_upload_multipart(
    image_path: Path,
    title: str,
    session_id: str,
    mime: str,
    width: int,
    height: int,
    form_state: dict[str, str],
) -> CurlMime:
    """Build the multipart payload matching browser form field order."""
    with image_path.open("rb") as f:
        file_bytes = f.read()

    mp = CurlMime()
    mp.addpart(name="redirect_uri", data=form_state["redirect_uri"].encode())
    mp.addpart(name="wg", data=form_state["wg"].encode())
    mp.addpart(name="wg_hmac", data=form_state["wg_hmac"].encode())
    mp.addpart(name="realm", data=form_state["realm"].encode())
    mp.addpart(name="appid", data=b"767")
    mp.addpart(name="consumer_app_id", data=b"767")
    mp.addpart(name="sessionid", data=session_id.encode())
    mp.addpart(name="token", data=form_state["token"].encode())
    mp.addpart(name="cloudfilenameprefix", data=form_state["cloudfilenameprefix"].encode())
    mp.addpart(name="publishedfileid", data=b"0")
    mp.addpart(name="id", data=b"0")
    mp.addpart(name="file_type", data=b"3")
    mp.addpart(name="image_width", data=str(width).encode())
    mp.addpart(name="image_height", data=str(height).encode())
    mp.addpart(name="title", data=title.encode())
    mp.addpart(name="file", filename=image_path.name, content_type=mime, data=file_bytes)
    mp.addpart(name="description", data=b"")
    mp.addpart(name="visibility", data=b"0")
    mp.addpart(name="agree_terms", data=b"on")
    return mp


def interpret_upload_response(response) -> bool:
    """Interpret Steam's redirect response for upload success."""
    if response.status_code not in {302, 303}:
        console.print(f"  [red]Upload failed (HTTP {response.status_code})[/]")
        return False

    redirect_url = response.headers.get("location", "")
    if "fileuploadsuccess=1" in redirect_url:
        return True

    result_match = re.search(r"fileuploadsuccess=(\d+)", redirect_url)
    if result_match:
        console.print(f"  [red]Steam returned EResult={result_match.group(1)}[/]")
    else:
        console.print("  [red]Upload failed — unexpected response[/]")
    return False


def collect_images(path: str) -> list[Path]:
    """Return a list of image file paths from a file or directory."""
    resolved = Path(path).expanduser()
    if resolved.is_file():
        return [resolved] if is_supported_image(resolved) else []

    if resolved.is_dir():
        return sorted(
            child for child in resolved.iterdir()
            if child.is_file() and is_supported_image(child)
        )

    return []


def upload_image(
    image_path: Path,
    title: str,
    session_id: str,
    login_secure: str,
    request_timeout: float,
) -> bool:
    """Upload a single image as Steam community artwork. Returns True on success."""
    cookies = {
        "sessionid": session_id,
        "steamLoginSecure": login_secure,
    }

    try:
        image_info = validate_image_file(image_path)
        if not image_info:
            return False
        mime, width, height = image_info

        form_state = fetch_form_state(cookies, request_timeout)
        if not form_state:
            return False

        multipart = build_upload_multipart(
            image_path=image_path,
            title=title,
            session_id=session_id,
            mime=mime,
            width=width,
            height=height,
            form_state=form_state,
        )
        response = requests.post(
            form_state["upload_url"],
            multipart=multipart,
            cookies=cookies,
            headers={
                "Referer": "https://steamcommunity.com/",
                "Origin": "https://steamcommunity.com",
            },
            allow_redirects=False,
            impersonate="chrome",
            timeout=request_timeout,
        )
        return interpret_upload_response(response)

    except FileNotFoundError:
        console.print(f"  [red]File not found:[/] {image_path}")
        return False
    except requests.exceptions.Timeout as e:
        console.print(f"  [red]Steam request timed out after {request_timeout}s:[/] {e}")
        return False
    except requests.exceptions.RequestException as e:
        console.print(f"  [red]Steam request failed:[/] {e}")
        return False
    except OSError as e:
        console.print(f"  [red]File error:[/] {e}")
        return False
    except Exception as e:
        console.print(f"  [red]Error:[/] {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload images to Steam community artwork.")
    parser.add_argument("path", help="Image file or folder of images to upload")
    parser.add_argument(
        "quantity",
        type=positive_int,
        nargs="?",
        default=1,
        help="Number of times to upload each image (default: 1)",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=5.0,
        help="Seconds between uploads (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help=f"Seconds to wait for Steam requests (default: {DEFAULT_REQUEST_TIMEOUT:g})",
    )
    parser.add_argument("--reset-cookies", action="store_true", help="Clear saved cookies and enter new ones")
    args = parser.parse_args()

    if args.reset_cookies:
        clear_cookies()

    images = collect_images(args.path)
    if not images:
        console.print(f"[bold red]No supported PNG/JPEG images found:[/] {args.path}")
        raise SystemExit(1)

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
            filename = image_path.name
            label = f"[{upload_num}/{total}] {filename}"
            if args.quantity > 1:
                label += f" (round {r + 1}/{args.quantity})"

            with Status(f"[bold cyan]Uploading {filename}...[/]", console=console, spinner="dots"):
                result = upload_image(
                    image_path=image_path,
                    title=random_title,
                    session_id=session_id,
                    login_secure=login_secure,
                    request_timeout=args.timeout,
                )

            if result:
                console.print(f"  [green]OK[/green]  {label}")
                success += 1
            else:
                console.print(f"  [red]FAIL[/red]  {label}")

            if upload_num < total:
                with Status(f"[dim]Waiting {args.delay}s...[/]", console=console, spinner="dots"):
                    time.sleep(args.delay)

    color = "green" if success == total else ("yellow" if success > 0 else "red")
    console.print(f"\n[bold {color}]Done: {success}/{total} uploaded successfully.[/]\n")

    if success < total:
        raise SystemExit(1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
