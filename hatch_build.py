import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        ui_dir = Path(self.root) / "src" / "histserv" / "dashboard" / "ui"
        subprocess.run(["bun", "install"], cwd=ui_dir, check=True)
        subprocess.run(["bun", "run", "build"], cwd=ui_dir, check=True)
