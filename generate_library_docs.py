#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

EXCLUDE_DIRS = {'__pycache__', '.git', 'venv', '.venv', 'env', '.env', 'site-packages'}

def get_file_author(file_path):
    """Get the author of a file using git blame."""
    try:
        # Get the first commit that added this file
        result = subprocess.run(
            ['git', 'log', '--diff-filter=A', '--format=%an', '--', str(file_path)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split('\n')[-1]  # Get the last line (first commit)
    except subprocess.CalledProcessError:
        return "Unknown"

def process_file(file_path):
    """Process a file and return its content with metadata."""
    file_path = Path(file_path).resolve()  # Ensure file_path is an absolute Path object
    try:
        with file_path.open('r', encoding='utf-8') as f:
            content = f.read()
        
        author = get_file_author(file_path)
        cwd = Path.cwd().resolve()
        try:
            relative_path = file_path.relative_to(cwd)
        except ValueError:
            relative_path = file_path.name  # Fallback to just the file name
        
        if file_path.suffix == '.py':
            return f"## {relative_path}\n\n**Author:** {author}\n\n```python\n{content}\n```\n\n"
        elif file_path.suffix == '.xml':
            return f"## {relative_path}\n\n**Author:** {author}\n\n```xml\n{content}\n```\n\n"
    except Exception as e:
        return f"## {file_path}\n\n**Error reading file:** {str(e)}\n\n"

def should_skip(file_path):
    file_path = Path(file_path)
    # Skip excluded directories, .pyc/.pyo files, __init__.py, the script itself
    if (
        any(exclude in file_path.parts for exclude in EXCLUDE_DIRS) or
        file_path.suffix in {'.pyc', '.pyo'} or
        file_path.name == '__init__.py' or
        'generate_library_docs.py' in str(file_path)
    ):
        return True
    return False

def main():
    # Create the output file
    with open('library-comprehensive.md', 'w', encoding='utf-8') as f:
        f.write("# Genesis Library Comprehensive Documentation\n\n")
        f.write("This document contains all user Python and XML files in the Genesis library.\n\n")
        
        # Find all .py and .xml files
        for root, dirs, files in os.walk('.'):
            # Exclude unwanted directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if file.endswith(('.py', '.xml')):
                    file_path = Path(root) / file
                    if not should_skip(file_path):
                        f.write(process_file(file_path))

if __name__ == '__main__':
    main() 