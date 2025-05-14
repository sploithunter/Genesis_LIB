#!/usr/bin/env python3

import subprocess
import json
from datetime import datetime
import os
from pathlib import Path

def run_git_command(command):
    """Run a git command and return its output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}")
        return None

def get_commit_history():
    """Get all commits in the repository."""
    # Get all commits with their details
    format_str = '--pretty=format:{"hash":"%H","author":"%an","date":"%ad","message":"%s"}'
    commits = run_git_command(['git', 'log', format_str])
    
    if not commits:
        return []
    
    # Parse the commits
    commit_list = []
    for commit in commits.split('\n'):
        try:
            commit_data = json.loads(commit)
            commit_list.append(commit_data)
        except json.JSONDecodeError:
            continue
    
    return commit_list

def get_changed_files(commit_hash):
    """Get files changed in a specific commit."""
    files = run_git_command(['git', 'show', '--name-only', '--pretty=format:', commit_hash])
    if files:
        return [f.strip() for f in files.split('\n') if f.strip()]
    return []

def get_file_content_at_commit(commit_hash, file_path):
    """Get the content of a file at a specific commit."""
    try:
        content = run_git_command(['git', 'show', f'{commit_hash}:{file_path}'])
        return content
    except:
        return None

def format_code_block(content):
    """Format code content for markdown."""
    if not content:
        return ""
    return f"```\n{content}\n```"

def main():
    # Create docs directory if it doesn't exist
    docs_dir = Path('docs')
    docs_dir.mkdir(exist_ok=True)
    
    # Get commit history
    commits = get_commit_history()
    
    # Start building markdown content
    markdown_content = "# Commit History\n\n"
    markdown_content += "This document contains a chronological history of all commits in the repository.\n\n"
    
    # Process each commit
    for commit in commits:
        commit_hash = commit['hash']
        print(f"Processing commit: {commit_hash}")
        
        # Add commit header
        markdown_content += f"## Commit: {commit_hash[:8]}\n\n"
        markdown_content += f"**Author:** {commit['author']}\n"
        markdown_content += f"**Date:** {commit['date']}\n"
        markdown_content += f"**Message:** {commit['message']}\n\n"
        
        # Get and process changed files
        changed_files = get_changed_files(commit_hash)
        if changed_files:
            markdown_content += "### Changed Files\n\n"
            
            for file_path in changed_files:
                content = get_file_content_at_commit(commit_hash, file_path)
                if content:
                    markdown_content += f"#### {file_path}\n\n"
                    markdown_content += format_code_block(content)
                    markdown_content += "\n\n"
        
        markdown_content += "---\n\n"
    
    # Write to markdown file
    with open(docs_dir / 'commit_history.md', 'w') as f:
        f.write(markdown_content)

if __name__ == '__main__':
    main() 