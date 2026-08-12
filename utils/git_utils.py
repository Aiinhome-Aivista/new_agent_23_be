import os
import subprocess
import shutil
import tempfile
import stat
from typing import Optional

def on_rm_error(func, path, exc_info):
    """
    Error handler for shutil.rmtree on Windows.
    Clears the read-only bit and retries deletion.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def clone_repo(git_url: str, branch: Optional[str] = None) -> str:
    """
    Clones a Git repository to a temporary directory and returns the absolute path.
    """
    temp_dir = tempfile.mkdtemp(prefix="utgc_git_")
    cmd = ["git", "-c", "credential.helper=", "clone", "--depth", "1"]
    if branch:
        cmd.extend(["-b", branch])
    cmd.extend([git_url, temp_dir])
    
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        # Clean up directory if clone failed
        shutil.rmtree(temp_dir, onerror=on_rm_error)
        raise Exception(f"Failed to clone repository: {result.stderr or result.stdout}")
    return temp_dir

def get_code_files(repo_path: str, target_subpath: Optional[str] = None, max_size_bytes: int = 150000) -> str:
    """
    Recursively finds and reads relevant source code files inside the repository,
    excluding tests, build folders, and dependency folders.
    Caps the total read content size to prevent LLM context overflow.
    """
    search_path = repo_path
    if target_subpath:
        # Normalize and clean target subpath
        clean_subpath = target_subpath.strip("/\\")
        search_path = os.path.join(repo_path, clean_subpath)
        if not os.path.exists(search_path):
            search_path = repo_path # fallback if subpath is missing

    allowed_extensions = {
        '.java', '.py', '.ts', '.tsx', '.cs', '.js', '.go', '.cpp', '.h', '.rb', '.php', '.swift', '.kt', '.m'
    }
    
    exclude_dirs = {
        '.git', 'node_modules', 'venv', 'env', 'build', 'target', 'dist', 
        'test', 'tests', '__pycache__', '.idea', '.vscode', 'gradle', '.settings', 'bin', 'obj'
    }

    code_context = []
    total_size = 0
    
    for root, dirs, files in os.walk(search_path):
        # Prune excluded directories in-place
        dirs[:] = [d for d in dirs if d.lower() not in exclude_dirs and 'test' not in d.lower()]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in allowed_extensions:
                file_path = os.path.join(root, file)
                # Skip test files by name check
                if 'test' in file.lower() or 'spec' in file.lower():
                    continue
                try:
                    file_size = os.path.getsize(file_path)
                    if total_size + file_size > max_size_bytes:
                        code_context.append("\n... [Remaining codebase truncated due to context limits] ...\n")
                        return "\n".join(code_context)
                    
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                    rel_path = os.path.relpath(file_path, repo_path)
                    code_context.append(f"=== File: {rel_path} ===\n{content}\n")
                    total_size += file_size
                except Exception:
                    continue
                    
    return "\n".join(code_context)

def cleanup_repo(repo_path: str):
    """
    Deletes the cloned repository directory safely.
    """
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path, onerror=on_rm_error)

def validate_git_connection(git_url: str) -> bool:
    """
    Checks if the Git repository URL is accessible and the credentials/token are valid
    using git ls-remote.
    """
    if not git_url:
        return True
    
    cmd = ["git", "-c", "credential.helper=", "ls-remote", git_url]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
        return result.returncode == 0
    except Exception:
        return False

