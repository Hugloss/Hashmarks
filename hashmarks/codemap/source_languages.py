from __future__ import annotations

SOURCE_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".sql": "sql",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
}

SOURCE_SUFFIXES = frozenset(SOURCE_LANGUAGES)
