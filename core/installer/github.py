"""
core/installer/github.py — GitHub Releases API Client

Interacts with the GitHub Releases API to discover available versions,
select matching architecture assets, and extract checksums while managing
rate limits and authorization tokens.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Sequence

import requests

from core.installer.arch import PlatformArch, PlatformOS, score_asset_match

logger = logging.getLogger(__name__)

_DEFAULT_API_TIMEOUT = (10, 30)
_SHA256_REGEX = re.compile(r"\b([a-fA-F0-9]{64})\b")


class GitHubRateLimitError(RuntimeError):
    """Raised when GitHub API rate limits are exceeded and max wait time is exceeded."""


class GitHubReleaseClient:
    """
    Client for interacting with GitHub Releases API.
    """

    def __init__(self, token: str | None = None, max_rate_limit_wait: int = 60) -> None:
        self._token = token.strip() if token else None
        self._max_rate_limit_wait = max_rate_limit_wait
        self._session = requests.Session()

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AIO-Media-Server-Manager/0.1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request_with_retries(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> requests.Response:
        """
        Execute an HTTP GET request to GitHub API with rate-limit and backoff handling.
        """
        headers = self._get_headers()
        for attempt in range(max_retries):
            try:
                response = self._session.get(
                    url, headers=headers, params=params, timeout=_DEFAULT_API_TIMEOUT
                )
                if response.status_code == 200:
                    return response

                # Check for rate limiting (403 or 429)
                if response.status_code in (403, 429):
                    reset_header = response.headers.get("X-RateLimit-Reset")
                    retry_after = response.headers.get("Retry-After")

                    wait_seconds = 60
                    if retry_after and retry_after.isdigit():
                        wait_seconds = int(retry_after)
                    elif reset_header and reset_header.isdigit():
                        wait_seconds = max(1, int(reset_header) - int(time.time()))

                    if wait_seconds > self._max_rate_limit_wait:
                        raise GitHubRateLimitError(
                            f"GitHub API rate limit exceeded. Reset requires waiting {wait_seconds}s "
                            f"(max wait allowed: {self._max_rate_limit_wait}s). "
                            f"Consider configuring GITHUB_TOKEN in settings."
                        )

                    logger.warning(
                        "GitHub rate limit hit. Waiting %ds before retry (attempt %d/%d)...",
                        wait_seconds,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait_seconds)
                    continue

                if response.status_code == 404:
                    logger.warning("GitHub resource not found: %s", url)
                    return response

                logger.warning(
                    "GitHub API returned status %d for %s (attempt %d/%d)",
                    response.status_code,
                    url,
                    attempt + 1,
                    max_retries,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "GitHub request failed for %s: %s (attempt %d/%d)",
                    url,
                    exc,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(2**attempt)

        raise RuntimeError(f"Failed to fetch from GitHub API: {url} after {max_retries} attempts.")

    def get_latest_release(self, repo: str) -> dict[str, Any]:
        """
        Fetch the latest published release payload for a repository ('owner/repo').
        """
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        resp = self._request_with_retries(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Cannot get latest release for {repo} (status {resp.status_code})")
        return resp.json()

    def get_release_by_tag(self, repo: str, tag: str) -> dict[str, Any]:
        """
        Fetch a specific release by tag name ('owner/repo', 'v1.0.0').
        """
        clean_tag = tag.strip()
        url = f"https://api.github.com/repos/{repo}/releases/tags/{clean_tag}"
        resp = self._request_with_retries(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Cannot get release {tag} for {repo} (status {resp.status_code})")
        return resp.json()

    def list_releases(self, repo: str, count: int = 10) -> list[dict[str, Any]]:
        """
        List recent releases for a repository.
        """
        url = f"https://api.github.com/repos/{repo}/releases"
        resp = self._request_with_retries(url, params={"per_page": count})
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []

    def select_asset(
        self,
        release: dict[str, Any],
        arch: PlatformArch,
        target_os: PlatformOS = PlatformOS.LINUX,
        preferred_patterns: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """
        Find and return the best matching asset dict from a release payload.
        Raises ValueError if no matching asset can be found.
        """
        assets: list[dict[str, Any]] = release.get("assets", [])
        if not assets:
            raise ValueError(f"Release '{release.get('tag_name')}' contains no downloadable assets.")

        best_asset: dict[str, Any] | None = None
        best_score = -1

        for asset in assets:
            name = asset.get("name", "")
            score = score_asset_match(name, arch, target_os)
            if score < 0:
                continue

            # Additional boost if user/plugin supplied specific regex patterns
            if preferred_patterns:
                for pat in preferred_patterns:
                    if re.search(pat, name, re.IGNORECASE):
                        score += 100

            if score > best_score:
                best_score = score
                best_asset = asset

        if not best_asset:
            available_names = [a.get("name", "") for a in assets]
            raise ValueError(
                f"No compatible binary asset found for arch={arch.value}, os={target_os.value} "
                f"in release '{release.get('tag_name')}'. Available assets: {available_names}"
            )

        logger.debug(
            "Selected asset '%s' (score %d) for %s / %s",
            best_asset.get("name"),
            best_score,
            target_os.value,
            arch.value,
        )
        return best_asset

    def find_checksum(
        self,
        release: dict[str, Any],
        target_asset_name: str,
    ) -> str | None:
        """
        Attempt to discover an expected SHA256 checksum for target_asset_name.
        1. Checks for asset named '{target_asset_name}.sha256' or similar checksum files.
        2. Inspects release body text for a matching SHA256 line.
        """
        assets: list[dict[str, Any]] = release.get("assets", [])

        # 1. Search for dedicated checksum file for this specific asset
        for asset in assets:
            name = asset.get("name", "")
            if name.lower() in (
                f"{target_asset_name.lower()}.sha256",
                f"{target_asset_name.lower()}.sha256sum",
                f"{target_asset_name.lower()}.sha512",
            ):
                download_url = asset.get("browser_download_url")
                if download_url:
                    content = self._download_text(download_url)
                    match = _SHA256_REGEX.search(content)
                    if match:
                        return match.group(1).lower()

        # 2. Search for bundled checksum files like SHA256SUMS, checksums.txt
        for asset in assets:
            name = asset.get("name", "").lower()
            if any(k in name for k in ("sha256sum", "checksums.txt", "checksums")):
                download_url = asset.get("browser_download_url")
                if download_url:
                    content = self._download_text(download_url)
                    for line in content.splitlines():
                        if target_asset_name in line:
                            match = _SHA256_REGEX.search(line)
                            if match:
                                return match.group(1).lower()

        # 3. Check the release description / body
        body = release.get("body") or ""
        for line in body.splitlines():
            if target_asset_name in line:
                match = _SHA256_REGEX.search(line)
                if match:
                    return match.group(1).lower()

        return None

    def _download_text(self, url: str) -> str:
        """Download small text file (like checksum file)."""
        try:
            resp = self._session.get(url, headers=self._get_headers(), timeout=_DEFAULT_API_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException as exc:
            logger.debug("Failed to download checksum text from %s: %s", url, exc)
        return ""
