"""Resolve showcase assets correctly for all locale URLs and local previews."""

import re

from mkdocs.utils import get_relative_url


def on_page_content(html, page, config, files):
    prefix = get_relative_url("assets/", page.url).removesuffix("assets/").rstrip("/")
    if 'class="aio-landing"' in html:
        # Raw HTML links bypass MkDocs' Markdown link processor. Home pages
        # live at each locale root, so these routes stay inside that locale.
        html = re.sub(
            r'href="((?:deploy/)?[A-Z_]+)\.md(#[^"]*)?"',
            lambda match: f'href="{match[1]}/{match[2] or ""}"',
            html,
        )
    return html.replace("__AIO_ASSET__/", f"{prefix}/" if prefix else "")
