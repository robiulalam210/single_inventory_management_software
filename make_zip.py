
from pathlib import Path
import zipfile

project = Path(r"E:\Project\single_inventory_management_software")
output = Path(r"E:\Project\single_inventory_management_software.zip")

exclude_dirs = {
    ".venv", "venv", "__pycache__", ".git",
    ".idea", ".vscode", "node_modules"
}

exclude_files = {".env", "db.sqlite3"}

with zipfile.ZipFile(
    output, "w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9
) as archive:

    for path in project.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(project)

        if any(part in exclude_dirs for part in relative.parts):
            continue

        if path.name in exclude_files:
            continue

        if path.suffix == ".pyc":
            continue

        if path.resolve() == output.resolve():
            continue

        archive.write(path, relative.as_posix())

print("ZIP created successfully!")
print(f"Location: {output}")
print(f"Size: {output.stat().st_size / (1024 * 1024):.2f} MB")
