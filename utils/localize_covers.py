#!/usr/bin/env python3

import re
import sys
from html import unescape
from http.client import HTTPResponse
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}

IMG_RE: re.Pattern[str] = re.compile(
    r"(?P<indent>^[ \t]*)"
    + r'(?P<tag><img\b[^>]*\bsrc="(?P<src>https?://[^"]+)"[^>]*>)',
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

ALT_RE: re.Pattern[str] = re.compile(
    r'\balt="([^"]*)"',
    re.IGNORECASE,
)


def slugify(text: str) -> str:
    """Convert text into a filesystem-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")

    return text[:60] or "cover"


def download_image(url: str) -> tuple[bytes, str]:
    """Download an image and determine its extension."""
    request = Request(
        unescape(url),
        headers={
            "User-Agent": "Mozilla/5.0 SmolWeb-cover-archiver/1.0",
            "Accept": "image/*,*/*;q=0.8",
        },
    )

    response = cast(
        HTTPResponse,
        urlopen(request, timeout=60),
    )

    with response:
        data: bytes = response.read()
        content_type: str = response.headers.get_content_type()

    extension = IMAGE_TYPES.get(content_type)

    if extension is None:
        raise RuntimeError(f"Unsupported content type: {content_type}")

    return data, extension


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 utils/localize_covers.py music/2026.html")
        return 1

    # Assuming:
    # root/
    # ├── music/
    # │   └── 2026.html
    # └── utils/
    #     └── localize_covers.py
    # Therefore parent.parent is the repository root.
    repo_root = Path(__file__).resolve().parent.parent

    input_path = Path(sys.argv[1])

    # Support both:
    #   music/2026.html
    # and:
    #   /absolute/path/to/music/2026.html
    if input_path.is_absolute():
        html_file = input_path.resolve()
    else:
        html_file = (repo_root / input_path).resolve()

    if not html_file.exists():
        print(
            f"HTML file does not exist: {html_file}",
            file=sys.stderr,
        )
        return 1

    if not html_file.is_file():
        print(
            f"Not a file: {html_file}",
            file=sys.stderr,
        )
        return 1

    year = html_file.stem

    output_dir = html_file.parent / "covers" / year
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        relative_output_dir = output_dir.relative_to(repo_root)

    except ValueError:
        message = (
            "HTML file must be located inside the repository.\n"
            + f"Repository root: {repo_root}\n"
            + f"HTML file:       {html_file}"
        )

        print(
            message,
            file=sys.stderr,
        )

        return 1

    web_prefix = "/" + relative_output_dir.as_posix()

    source = html_file.read_text(
        encoding="utf-8",
    )

    downloaded: dict[str, str] = {}
    failures = 0

    def replace_image(match: re.Match[str]) -> str:
        nonlocal failures

        indent = match.group("indent")
        tag = match.group("tag")
        source_url = match.group("src")

        alt_match = ALT_RE.search(tag)

        if alt_match:
            alt = unescape(alt_match.group(1))
        else:
            alt = "cover"

        try:
            if source_url not in downloaded:
                data, extension = download_image(source_url)

                filename = f"{slugify(alt)}{extension}"

                output_path = output_dir / filename

                _ = output_path.write_bytes(data)

                downloaded[source_url] = f"{web_prefix}/{filename}"

                print(f"Downloaded: {source_url}\n" + f"         -> {output_path}")

            local_url = downloaded[source_url]

        except Exception as exc:
            failures += 1

            print(
                f"FAILED: {source_url}\n" + f"        {exc}",
                file=sys.stderr,
            )

            # Keep the original remote image untouched
            # if downloading fails.
            return match.group(0)

        new_tag = tag.replace(
            f'src="{source_url}"',
            f'src="{local_url}"',
            1,
        )

        # Preserve indentation for multi-line <img> tags.
        indented_tag = new_tag.replace("\n", "\n" + indent + "  ")

        return (
            f'{indent}<a class="cover-source" '
            + f'href="{source_url}">\n'
            + f"{indent}  {indented_tag}\n"
            + f"{indent}</a>"
        )

    new_source = IMG_RE.sub(replace_image, source)
    _ = html_file.write_text(new_source, encoding="utf-8")

    print()
    print(f"Localized images: {len(downloaded)}")
    print(f"Failures: {failures}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
