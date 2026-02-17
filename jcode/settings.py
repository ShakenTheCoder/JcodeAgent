"""
User settings and persistent configuration.
Stored in ~/.jcode/settings.json

v0.7.0 — Added git settings, CWD mode, agentic/chat mode preferences.
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class UserSettings:
    """Persistent user settings."""
    default_output_dir: str = "~/jcode_projects"
    auto_save_sessions: bool = True
    last_project: str = ""
    autonomous_access: bool | None = None   # None = never asked
    internet_access: bool | None = None     # None = never asked

    # v0.7.0 — Git integration
    git_auto_commit: bool = True            # Auto-commit after builds/modifications
    git_auto_push: bool = False             # Auto-push after commits (needs remote)
    git_default_remote: str = "origin"

    # v0.7.0 — Mode preference
    default_mode: str = "agentic"           # "agentic" or "chat"

    # v0.7.0 — CWD mode (operate in current directory)
    cwd_mode: bool = True                   # Use CWD instead of ~/jcode_projects

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> UserSettings:
        # Filter to known fields only for forward-compat
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class SettingsManager:
    """Manages user settings persistence."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".jcode"
        self.settings_file = self.config_dir / "settings.json"
        self.projects_dir = self.config_dir / "projects"
        self.settings = self._load_settings()
    
    def _load_settings(self) -> UserSettings:
        """Load settings from disk or create defaults."""
        if self.settings_file.exists():
            try:
                data = json.loads(self.settings_file.read_text())
                return UserSettings.from_dict(data)
            except Exception:
                pass
        return UserSettings()
    
    def save_settings(self) -> None:
        """Persist settings to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(
            json.dumps(self.settings.to_dict(), indent=2)
        )
    
    def is_first_run(self) -> bool:
        """Check if this is the user's first time running JCode."""
        return not self.settings_file.exists()
    
    def get_default_output_dir(self) -> Path:
        """Return the default output directory as a Path."""
        return Path(self.settings.default_output_dir).expanduser().resolve()
    
    def set_default_output_dir(self, path: str | Path) -> None:
        """Update the default output directory."""
        self.settings.default_output_dir = str(path)
        self.save_settings()
    
    def get_projects_dir(self) -> Path:
        """Get the directory where project metadata is stored."""
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        return self.projects_dir
    
    def list_projects(self) -> list[dict]:
        """List all saved projects with metadata."""
        projects = []
        if self.projects_dir.exists():
            for proj_file in self.projects_dir.glob("*.json"):
                try:
                    data = json.loads(proj_file.read_text())
                    projects.append(data)
                except Exception:
                    continue
        return sorted(projects, key=lambda p: p.get("last_modified", ""), reverse=True)
    
    def save_project_metadata(self, project_data: dict) -> None:
        """Save project metadata for later resumption."""
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        
        # Use project name as filename (sanitized)
        name = project_data.get("name", "unnamed")
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
        safe_name = safe_name.strip().replace(" ", "_").lower()
        
        proj_file = self.projects_dir / f"{safe_name}.json"
        proj_file.write_text(json.dumps(project_data, indent=2))
        
        self.settings.last_project = str(proj_file)
        self.save_settings()
    
    def load_project_metadata(self, project_name: str) -> dict | None:
        """Load project metadata by name."""
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in project_name)
        safe_name = safe_name.strip().replace(" ", "_").lower()
        
        proj_file = self.projects_dir / f"{safe_name}.json"
        if proj_file.exists():
            return json.loads(proj_file.read_text())
        return None
    
    def get_last_project(self) -> dict | None:
        """Get the most recently worked on project."""
        if self.settings.last_project and Path(self.settings.last_project).exists():
            try:
                return json.loads(Path(self.settings.last_project).read_text())
            except Exception:
                pass
        return None
