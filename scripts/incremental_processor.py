import os
import subprocess

STATE_FILE = ".last_processed_commit"

def get_current_commit():
    """Returns the current HEAD commit hash."""
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: Not a git repository or git is not installed.")
        return None
    return result.stdout.strip()

def get_changed_files(last_commit, current_commit):
    """Returns a list of changed files between last_commit and current_commit."""
    result = subprocess.run(
        ["git", "diff", "--name-only", last_commit, current_commit],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Error getting diff between {last_commit} and {current_commit}")
        return []
    
    files = result.stdout.strip().split("\n")
    # Filter out empty strings
    return [f for f in files if f.strip()]

def process_file(filepath):
    """
    Placeholder function for actual processing logic.
    Replace this with what you actually want to do with the changed files.
    """
    if not os.path.exists(filepath):
        print(f"[-] File skipped (maybe deleted): {filepath}")
        return
    
    print(f"[+] Processing file: {filepath}")
    # TODO: Add your custom processing logic here.
    # Example: run a linter, generate documentation, summarize code, etc.

def main():
    current_commit = get_current_commit()
    if not current_commit:
        return

    last_commit = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            last_commit = f.read().strip()

    if not last_commit:
        print("No previous state found. This is the first run.")
        print("You may want to process all files initially, or just set the baseline.")
        print(f"Saving current commit {current_commit} as the baseline.")
        # If you want to process all files on the first run, add that logic here.
        
        with open(STATE_FILE, "w") as f:
            f.write(current_commit)
        return

    if last_commit == current_commit:
        print("No new commits. Everything is up to date.")
        return

    print(f"Changes detected. Finding changed files from {last_commit} to {current_commit} ...")
    
    changed_files = get_changed_files(last_commit, current_commit)
    
    if not changed_files:
        print("No files were changed in the new commits.")
    else:
        for file in changed_files:
            process_file(file)

    # Update state after successful processing
    with open(STATE_FILE, "w") as f:
        f.write(current_commit)
    print("State updated successfully.")

if __name__ == "__main__":
    main()
