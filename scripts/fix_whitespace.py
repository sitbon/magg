#!/usr/bin/env python3
"""Fix trailing whitespace and ensure newline at end of files.
"""
import os
import sys


def fix_file(filepath):
    """Fix trailing whitespace and ensure newline at end of file.
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()

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
        with open(filepath, 'w') as f:
            f.writelines(lines)
        return True

    return False


def main():
    """Process all Python files."""
    fixed_files = []

    for line in sys.stdin:
        filepath = line.strip()
        if filepath and os.path.exists(filepath):
            if fix_file(filepath):
                fixed_files.append(filepath)

    if fixed_files:
        print(f"Fixed {len(fixed_files)} files:")
        for f in fixed_files:
            print(f"  {f}")
    else:
        print("No files needed fixing")

if __name__ == "__main__":
    main()
