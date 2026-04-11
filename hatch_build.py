from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        dist_dir = Path(self.root) / "src" / "histserv" / "dashboard" / "ui" / "dist"
        if not dist_dir.is_dir():
            msg = (
                "Dashboard UI not pre-built. "
                "Run 'pixi run -e dashboard dashboard-build' before packaging."
            )
            raise RuntimeError(msg)
