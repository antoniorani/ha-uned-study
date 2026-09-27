"""Atomic synchronization of subject content from GitHub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
from urllib.parse import quote, urlparse

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .loader import scan_subjects

_LOGGER = logging.getLogger(__name__)

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 300 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 30 * 1024 * 1024

_GITHUB_REPO_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)


class ContentSyncError(RuntimeError):
    """Raised when remote content cannot be safely activated."""


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """Normalized GitHub repository coordinates."""

    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True, slots=True)
class SyncReport:
    """Result of a successful content synchronization."""

    repository: str
    branch: str
    subject_count: int
    synced_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "branch": self.branch,
            "subject_count": self.subject_count,
            "synced_at": self.synced_at,
        }


def parse_github_repository(value: str) -> GitHubRepository:
    """Accept a normal github.com repository URL or owner/name."""
    candidate = value.strip()

    if _GITHUB_REPO_RE.fullmatch(candidate):
        owner, name = candidate.split("/", 1)
        return GitHubRepository(owner=owner, name=name.removesuffix(".git"))

    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.hostname not in {
        "github.com",
        "www.github.com",
    }:
        raise ValueError("Only https://github.com repositories are supported")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValueError("Repository URL must identify exactly owner/repository")

    owner, name = parts
    name = name.removesuffix(".git")
    if not _GITHUB_REPO_RE.fullmatch(f"{owner}/{name}"):
        raise ValueError("Invalid GitHub repository name")
    return GitHubRepository(owner=owner, name=name)


class GitHubContentSynchronizer:
    """Download, validate and atomically activate a GitHub content snapshot."""

    def __init__(
        self,
        *,
        data_dir: Path,
        content_dir: Path,
        repository: str,
        branch: str,
    ) -> None:
        self.data_dir = data_dir
        self.content_dir = content_dir
        self.repository = parse_github_repository(repository)
        self.branch = branch.strip()
        if not self.branch:
            raise ValueError("GitHub branch must not be empty")

        self.last_report: SyncReport | None = None
        self.last_error: str | None = None

    @property
    def source(self) -> dict[str, object]:
        """Describe the configured source and latest in-memory status."""
        return {
            "repository": self.repository.slug,
            "branch": self.branch,
            "last_sync": (
                self.last_report.as_dict() if self.last_report else None
            ),
            "last_error": self.last_error,
        }

    async def async_sync(self, hass: HomeAssistant) -> SyncReport:
        """Synchronize content without replacing active data until validation passes."""
        try:
            archive = await self._async_download(hass)
            report = await hass.async_add_executor_job(
                self._install_archive, archive
            )
        except Exception as exc:
            self.last_error = str(exc)
            raise
        self.last_report = report
        self.last_error = None
        return report

    async def _async_download(self, hass: HomeAssistant) -> bytes:
        ref = quote(self.branch, safe="")
        url = (
            f"https://codeload.github.com/{self.repository.owner}/"
            f"{self.repository.name}/tar.gz/{ref}"
        )
        session = async_get_clientsession(hass)
        try:
            async with session.get(
                url,
                timeout=ClientTimeout(total=90),
                headers={"Accept": "application/octet-stream"},
            ) as response:
                if response.status != 200:
                    raise ContentSyncError(
                        f"GitHub returned HTTP {response.status}"
                    )
                content_length = response.content_length
                if (
                    content_length is not None
                    and content_length > MAX_ARCHIVE_BYTES
                ):
                    raise ContentSyncError(
                        "Content archive exceeds the configured size limit"
                    )
                data = await response.read()
        except (ClientError, TimeoutError) as exc:
            raise ContentSyncError(
                f"Could not download content from GitHub: {exc}"
            ) from exc

        if not data:
            raise ContentSyncError("GitHub returned an empty archive")
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ContentSyncError(
                "Content archive exceeds the configured size limit"
            )
        return data

    def _install_archive(self, archive: bytes) -> SyncReport:
        self.data_dir.mkdir(parents=True, exist_ok=True)

        staging_parent = Path(
            tempfile.mkdtemp(
                prefix=".content-staging-",
                dir=self.data_dir,
            )
        )
        staged_content = staging_parent / "content"
        staged_content.mkdir()

        backup_dir = self.data_dir / ".content-backup"
        active_moved = False

        try:
            self._extract_subjects(archive, staged_content)

            subjects, errors = scan_subjects(staged_content)
            if errors:
                details = "; ".join(
                    f"{subject}: {error}"
                    for subject, error in sorted(errors.items())
                )
                raise ContentSyncError(
                    f"Downloaded content failed validation: {details}"
                )
            if not subjects:
                raise ContentSyncError(
                    "Downloaded repository contains no valid subjects"
                )

            if backup_dir.exists():
                shutil.rmtree(backup_dir)

            if self.content_dir.exists():
                os.replace(self.content_dir, backup_dir)
                active_moved = True

            try:
                os.replace(staged_content, self.content_dir)
            except Exception:
                if active_moved and backup_dir.exists():
                    os.replace(backup_dir, self.content_dir)
                    active_moved = False
                raise

            active_moved = False
            if backup_dir.exists():
                try:
                    shutil.rmtree(backup_dir)
                except OSError as exc:
                    _LOGGER.warning(
                        "Could not remove old content backup: %s", exc
                    )

            return SyncReport(
                repository=self.repository.slug,
                branch=self.branch,
                subject_count=len(subjects),
                synced_at=datetime.now(timezone.utc).isoformat(),
            )
        except ContentSyncError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise ContentSyncError(
                f"Could not activate downloaded content: {exc}"
            ) from exc
        finally:
            if active_moved and not self.content_dir.exists():
                if backup_dir.exists():
                    os.replace(backup_dir, self.content_dir)
            shutil.rmtree(staging_parent, ignore_errors=True)

    def _extract_subjects(
        self,
        archive: bytes,
        destination: Path,
    ) -> None:
        expanded = 0
        member_count = 0
        seen_paths: set[PurePosixPath] = set()
        seen_subject_file = False

        with tarfile.open(
            fileobj=BytesIO(archive),
            mode="r:gz",
        ) as tar:
            for member in tar:
                member_count += 1
                if member_count > 20_000:
                    raise ContentSyncError(
                        "Archive contains too many entries"
                    )
                if member.isdir():
                    continue
                if not member.isfile():
                    continue
                if member.size < 0 or member.size > MAX_SINGLE_FILE_BYTES:
                    raise ContentSyncError(
                        f"Archive member is too large: {member.name}"
                    )

                path = PurePosixPath(member.name)
                parts = path.parts
                try:
                    subjects_index = parts.index("subjects")
                except ValueError:
                    continue

                relative_parts = parts[subjects_index + 1 :]
                if not relative_parts:
                    continue

                relative = PurePosixPath(*relative_parts)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or "." in relative.parts
                ):
                    raise ContentSyncError(
                        f"Unsafe archive path: {member.name}"
                    )

                # subjects/README.md is repository documentation, not content.
                if len(relative.parts) < 2:
                    continue

                expanded += member.size
                if expanded > MAX_EXPANDED_BYTES:
                    raise ContentSyncError(
                        "Expanded content exceeds the configured size limit"
                    )

                if relative in seen_paths:
                    raise ContentSyncError(
                        f"Duplicate archive path: {relative}"
                    )
                seen_paths.add(relative)

                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)

                source = tar.extractfile(member)
                if source is None:
                    raise ContentSyncError(
                        f"Could not read archive member: {member.name}"
                    )
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

                if target.name == "subject.json":
                    seen_subject_file = True

        if not seen_subject_file:
            raise ContentSyncError(
                "Archive does not contain subjects/*/subject.json"
            )
