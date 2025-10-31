Code Combiner for LLMs
======================

A fast, Git‑aware file combiner and code prep tool with a modern Qt UI. Merge many source files into a clean, single output — great for LLM prompts, reviews, or quick sharing. Includes a diff viewer and a file tree exporter.

Highlights
----------
- Gitignore‑aware scanning: honors `.gitignore` (toggleable) and your custom exclusions.
- Powerful exclusions: exclude by folder names, relative folders, file patterns, or explicit files; save/load profiles.
- Live preview with syntax highlight: quick peek for many languages; safe limits for huge files.
- Combine selected or all files: writes atomically; skips very large files with a clear note; binary files are summarized.
- File tree export: Unicode/ASCII styles, optional sizes, Markdown fenced output.
- Compare page: side‑by‑side or unified (git‑style) diffs; copy unified patch.
- Theming: System, Light variants, Dark, and ultra‑dark tints with tuned QSS.
- Persistent prefs: remembers folders, toggles, window state, UI scale, and last export directory.

Quick Start (GUI)
-----------------
1. Run the app (`python run.py` or the packaged binary).
2. Pick a folder (or drag & drop).
3. Tweak exclusions and search; preview files.
4. Generate combined output; save where you like.
5. Export a file tree or compare texts in the Compare page.

CLI (headless)
--------------
Use the core engine in scripts/CI:

    python -m src.cli <root> [-o out.txt] [--no-gitignore] \
        [--use-default-folder-names] \
        [--exclude-folder REL] [--exclude-file-pattern PAT] [--exclude-file ABS]

Example:

    python -m src.cli . -o combined.txt --use-default-folder-names \
        --exclude-file-pattern "*.log" --exclude-folder dist

Build/Package
-------------
PyInstaller spec files are included. For a quick run from source, install deps from `requirements.txt` and run `python run.py`.

License
-------
MIT
