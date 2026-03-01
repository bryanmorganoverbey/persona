import subprocess

def git_commit_and_push(repo_root: str, message: str) -> bool:
    """Stage all changes, pull latest changes before committing, and push."""
    try:
        # Configure Git user
        subprocess.run(
            ["git", "config", "user.name", "Goal Agent"],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "goal-agent@persona.local"],
            cwd=repo_root, check=True, capture_output=True,
        )

        # Pull the latest changes to avoid conflicts
        subprocess.run(
            ["git", "pull", "origin", "main", "--rebase"],
            cwd=repo_root, check=True, capture_output=True,
        )

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_root, check=True, capture_output=True,
        )

        # Check if there are staged changes
        diff = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            cwd=repo_root, capture_output=True,
        )
        if diff.returncode == 0:
            return False  # nothing to commit

        # Commit the changes
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_root, check=True, capture_output=True,
        )
        
        # Push the changes
        subprocess.run(
            ["git", "push"],
            cwd=repo_root, check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e.stderr.decode() if e.stderr else e}")
        return False
