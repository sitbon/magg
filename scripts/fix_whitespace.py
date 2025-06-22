#!/usr/bin/env python3
"""Fix trailing whitespace and ensure newline at end of files.

Recursively finds Python files in the current directory, excluding
hidden/dotted folders and __pycache__ directories.
"""
import sys
from pathlib import Path


def fix_file(filepath):
    """Fix trailing whitespace and ensure newline at end of file.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (UnicodeDecodeError, PermissionError) as e:
        print(f"Skipping {filepath}: {e}")
        return False

    if not lines:
        return False

    changed = False

    # Fix trailing whitespace on each line
    for i, line in enumerate(lines):
        cleaned = line.rstrip()
        if line != cleaned + '\n' and line != cleaned:
            lines[i] = cleaned + '\n' if cleaned or i < len(lines) - 1 else cleaned
            changed = True

    # Ensure file ends with newline
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
        changed = True

    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True

    return False


def find_python_files(root_dir='.'):
    """Find all Python files recursively, excluding hidden and cache directories.
    """
    root_path = Path(root_dir).resolve()

    for path in root_path.rglob('*.py'):
        # Skip if any parent directory starts with '.' or is __pycache__
        skip = False
        for parent in path.relative_to(root_path).parents:
            if parent.name.startswith('.') or parent.name == '__pycache__':
                skip = True
                break

        # Also check the file itself
        if path.name.startswith('.') or path.parent.name == '__pycache__':
            skip = True

        if not skip:
            yield path


def main():
    """Process all Python files in current directory tree."""
    # Determine root directory
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = '.'

    fixed_files = []
    total_files = 0

    print(f"Scanning for Python files in {Path(root_dir).resolve()}...")

    for filepath in find_python_files(root_dir):
        total_files += 1
        if fix_file(filepath):
            fixed_files.append(filepath)

    print(f"\nScanned {total_files} Python files.")

    if fixed_files:
        print(f"Fixed {len(fixed_files)} files:")
        for f in sorted(fixed_files):
            print(f"  {f}")
    else:
        print("No files needed fixing")


if __name__ == "__main__":
    main()
