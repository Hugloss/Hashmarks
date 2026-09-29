from __future__ import annotations

import json

from scripts import windows_published_upgrade_smoke as smoke


def test_previous_windows_release_selects_newest_qualified_stable_tag(
    monkeypatch,
) -> None:
    releases = [
        {
            "tag_name": tag,
            "draft": draft,
            "prerelease": prerelease,
            "assets": [{"name": name} for name in assets],
        }
        for tag, draft, prerelease, assets in (
            ("v0.25.0", False, False, ["hashmarks-windows-x86_64.exe"]),
            (
                "v0.24.0",
                False,
                False,
                ["hashmarks-windows-x86_64.exe", "install.ps1", "SHA256SUMS.txt"],
            ),
            (
                "v0.23.0",
                False,
                False,
                ["hashmarks-windows-x86_64.exe", "install.ps1", "SHA256SUMS.txt"],
            ),
            (
                "v0.24.1",
                False,
                True,
                ["hashmarks-windows-x86_64.exe", "install.ps1", "SHA256SUMS.txt"],
            ),
            (
                "v0.24.2",
                True,
                False,
                ["hashmarks-windows-x86_64.exe", "install.ps1", "SHA256SUMS.txt"],
            ),
        )
    ]
    monkeypatch.setattr(
        smoke, "_read_url", lambda url, *, token=None: json.dumps(releases).encode()
    )

    assert smoke._previous_windows_release("Hugloss/Hashmarks", "v0.25.0") == "v0.24.0"


def test_first_windows_release_has_explicit_no_prior_result(monkeypatch) -> None:
    monkeypatch.setattr(smoke, "_read_url", lambda url, *, token=None: b"[]")

    assert smoke._previous_windows_release("Hugloss/Hashmarks", "v0.24.0") is None
