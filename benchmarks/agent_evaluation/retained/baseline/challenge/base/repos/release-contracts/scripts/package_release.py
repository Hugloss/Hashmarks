from pathlib import Path

def package_release(artifact: Path) -> str:
    return artifact.name
