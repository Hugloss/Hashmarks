from pathlib import Path

from scripts.qualification_filesystem import windows_mounted_wsl_path


def test_windows_drive_mount_is_timing_warning_surface() -> None:
    assert windows_mounted_wsl_path(Path("/mnt/c/work/hashmarks"))
    assert windows_mounted_wsl_path(Path("/mnt/D/repo"))


def test_native_linux_paths_are_authoritative_timing_surfaces() -> None:
    assert not windows_mounted_wsl_path(Path("/home/developer/work/hashmarks"))
    assert not windows_mounted_wsl_path(Path("/tmp/hashmarks"))
    assert not windows_mounted_wsl_path(Path("/mnt/data/hashmarks"))
