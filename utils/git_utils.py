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
    cmd = ["git", "-c", "credential.helper=", "clone"]
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

def get_repo_head_commit(repo_path: str) -> str:
    """
    Retrieves the current HEAD commit hash of the repository.
    """
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

def get_modified_files(repo_path: str, since_commit: str, to_commit: str) -> list:
    """
    Gets files changed/added between two commits using git diff --name-only.
    """
    try:
        check_since = subprocess.run(["git", "cat-file", "-t", since_commit], cwd=repo_path, capture_output=True)
        check_to = subprocess.run(["git", "cat-file", "-t", to_commit], cwd=repo_path, capture_output=True)
        if check_since.returncode != 0 or check_to.returncode != 0:
            return []
            
        result = subprocess.run(
            ["git", "diff", "--name-only", since_commit, to_commit],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []

def get_code_files(repo_path: str, target_subpath: Optional[str] = None, max_size_bytes: int = 500000) -> str:
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
                # Skip test files, system prompts, pricing knowledge bases and slide generators
                if 'test' in file.lower() or 'spec' in file.lower() or 'prompts' in file.lower() or 'pptx' in file.lower() or 'pricing_kb' in file.lower():
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
    Checks if the Git repository URL is accessible and the credentials/token are valid.
    For public repos, git ls-remote succeeds anonymously even with a wrong token.
    Therefore, we also explicitly validate the token using the hosting provider's API.
    """
    if not git_url:
        return True
    
    # 1. Parse and validate the token via API if present
    try:
        import urllib.parse
        import requests
        
        parsed = urllib.parse.urlparse(git_url)
        host = parsed.hostname or ""
        token = parsed.password or parsed.username
        
        # Check if credential looks like a token
        if token and "@" in git_url:
            if "github.com" in host.lower():
                headers = {"Authorization": f"token {token}"}
                response = requests.get("https://api.github.com/user", headers=headers, timeout=5)
                if response.status_code == 401:
                    return False
            elif "gitlab.com" in host.lower():
                headers = {"PRIVATE-TOKEN": token}
                response = requests.get("https://gitlab.com/api/v4/user", headers=headers, timeout=5)
                if response.status_code == 401:
                    return False
    except Exception:
        pass # Fallback to git command if API call fails due to network/rate-limiting
        
    # 2. Run git command validation
    cmd = ["git", "-c", "credential.helper=", "ls-remote", git_url]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
        return result.returncode == 0
    except Exception:
        return False

