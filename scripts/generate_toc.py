#!/usr/bin/env python3
"""
Generate a Table of Contents for README.md based on markdown headings.

Usage:
    python scripts/generate_toc.py

This script:
1. Reads README.md
2. Extracts all markdown headings (## and lower, skipping # title)
3. Generates a hierarchical table of contents with anchor links
4. Inserts/updates the TOC between <!-- TOC --> markers
"""

import re
from pathlib import Path


def slugify(text):
    """Convert heading text to GitHub-compatible anchor link."""
    # GitHub anchor generation rules:
    # 1. Convert to lowercase
    # 2. Remove punctuation except hyphens and spaces
    # 3. Replace spaces with hyphens
    # 4. Remove multiple consecutive hyphens

    slug = text.lower()
    # Remove emoji and special characters, keep alphanumeric, spaces, and hyphens
    slug = re.sub(r'[^\w\s-]', '', slug)
    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')
    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    return slug


def extract_headings(content):
    """Extract all headings from markdown content."""
    headings = []

    # Match markdown headings (##, ###, etc., but not #)
    # Ignore headings inside code blocks
    in_code_block = False

    for line in content.split('\n'):
        # Track code blocks
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        # Match headings (## or more #'s, but not single #)
        match = re.match(r'^(#{2,})\s+(.+)$', line)
        if match:
            level = len(match.group(1))
            text = match.group(2).strip()

            # Skip if heading is already a link (like badges)
            if text.startswith('[') or text.startswith('<'):
                continue

            headings.append({
                'level': level,
                'text': text,
                'slug': slugify(text)
            })

    return headings


def generate_toc(headings):
    """Generate table of contents markdown from headings."""
    if not headings:
        return ""

    toc_lines = ["## Table of Contents\n"]

    # Find the minimum heading level to use as base
    min_level = min(h['level'] for h in headings)

    for heading in headings:
        # Skip the "Table of Contents" heading itself
        if heading['text'] == "Table of Contents":
            continue

        # Calculate indentation based on heading level
        indent_level = heading['level'] - min_level
        indent = '  ' * indent_level

        # Create markdown list item with link
        link = f"[{heading['text']}](#{heading['slug']})"
        toc_lines.append(f"{indent}- {link}")

    return '\n'.join(toc_lines)


def update_readme_toc(readme_path):
    """Update or insert TOC in README.md."""
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract headings
    headings = extract_headings(content)

    if not headings:
        print("No headings found in README.md")
        return False

    # Generate TOC
    toc = generate_toc(headings)

    # Check if TOC markers exist
    toc_start = '<!-- TOC -->'
    toc_end = '<!-- /TOC -->'

    if toc_start in content and toc_end in content:
        # Replace existing TOC
        pattern = re.compile(
            re.escape(toc_start) + r'.*?' + re.escape(toc_end),
            re.DOTALL
        )
        new_content = pattern.sub(
            f"{toc_start}\n\n{toc}\n\n{toc_end}",
            content
        )
        print("Updated existing TOC")
    else:
        # Insert TOC after the license badge and before first ## heading
        # Find the position after the license badge
        lines = content.split('\n')
        insert_pos = None

        for i, line in enumerate(lines):
            # Look for first ## heading (but skip if it's already "Table of Contents")
            if re.match(r'^##\s+(?!Table of Contents)', line):
                insert_pos = i
                break

        if insert_pos is not None:
            # Insert TOC markers and content
            toc_block = [
                '',
                toc_start,
                '',
                toc,
                '',
                toc_end,
                ''
            ]
            lines = lines[:insert_pos] + toc_block + lines[insert_pos:]
            new_content = '\n'.join(lines)
            print("Inserted new TOC")
        else:
            print("Could not find suitable position for TOC")
            return False

    # Write updated content
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"✓ Table of Contents generated with {len(headings)} headings")
    return True


def main():
    """Main entry point."""
    # Get project root (parent of scripts directory)
    project_root = Path(__file__).parent.parent
    readme_path = project_root / 'README.md'

    if not readme_path.exists():
        print(f"Error: README.md not found at {readme_path}")
        return 1

    success = update_readme_toc(readme_path)
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
