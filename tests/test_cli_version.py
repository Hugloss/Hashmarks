from __future__ import annotations

import pytest

from hashmarks._version import __version__
from hashmarks.cli import main


def test_cli_supports_conventional_version_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"hashmarks version {__version__}"
