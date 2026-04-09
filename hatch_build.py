import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        ui_dir = Path(self.root) / "dashboard" / "ui"
        subprocess.run(["bun", "install"], cwd=ui_dir, check=True)
        subprocess.run(["bun", "run", "build"], cwd=ui_dir, check=True)
        # Copy built assets into the package tree so hatchling includes them in the wheel.
        target = Path(self.root) / "src" / "histserv" / "dashboard" / "static"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(ui_dir / "dist", target)
