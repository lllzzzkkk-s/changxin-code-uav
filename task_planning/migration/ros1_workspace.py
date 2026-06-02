from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional


InstallMode = Literal["copy", "symlink"]

PACKAGE_NAME = "platform_gateway_msgs"
SERVICE_SYMBOL = "platform_gateway_msgs.srv:TaskCommandJson"


@dataclass(frozen=True)
class Ros1GatewayWorkspacePlan:
    catkin_src: Path
    repo_root: Path
    package_source: Path
    package_target: Path
    mode: InstallMode
    dry_run: bool
    installed: bool
    validation_errors: List[str]
    warnings: List[str]
    next_commands: List[str]
    schema: str = "Ros1GatewayWorkspacePlan.v1"

    @property
    def ok(self) -> bool:
        return not self.validation_errors

    def as_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["catkin_src"] = str(self.catkin_src)
        data["repo_root"] = str(self.repo_root)
        data["package_source"] = str(self.package_source)
        data["package_target"] = str(self.package_target)
        data["ok"] = self.ok
        return data


def prepare_ros1_gateway_workspace(
    *,
    repo_root: Path,
    catkin_src: Path,
    mode: InstallMode = "copy",
    apply: bool = False,
    force: bool = False,
) -> Ros1GatewayWorkspacePlan:
    repo_root = repo_root.resolve()
    catkin_src = catkin_src.expanduser().resolve()
    package_source = repo_root / "platform_gateway/ros/catkin_pkg" / PACKAGE_NAME
    package_target = catkin_src / PACKAGE_NAME
    errors = _validate_inputs(catkin_src=catkin_src, package_source=package_source, mode=mode)
    warnings: List[str] = []

    if package_target.exists() or package_target.is_symlink():
        if not force:
            warnings.append(f"{package_target} already exists; use --force to replace it")
        elif apply:
            _remove_existing(package_target)

    installed = False
    if apply and not errors:
        if (package_target.exists() or package_target.is_symlink()) and not force:
            errors.append(f"target package already exists: {package_target}")
        else:
            if mode == "copy":
                shutil.copytree(package_source, package_target, symlinks=True)
            else:
                package_target.symlink_to(package_source, target_is_directory=True)
            installed = True

    return Ros1GatewayWorkspacePlan(
        catkin_src=catkin_src,
        repo_root=repo_root,
        package_source=package_source,
        package_target=package_target,
        mode=mode,
        dry_run=not apply,
        installed=installed,
        validation_errors=errors,
        warnings=warnings,
        next_commands=_next_commands(repo_root=repo_root, catkin_src=catkin_src),
    )


def _validate_inputs(*, catkin_src: Path, package_source: Path, mode: str) -> List[str]:
    errors: List[str] = []
    if mode not in {"copy", "symlink"}:
        errors.append("mode must be copy or symlink")
    if not catkin_src.exists():
        errors.append(f"catkin src path does not exist: {catkin_src}")
    elif not catkin_src.is_dir():
        errors.append(f"catkin src path is not a directory: {catkin_src}")
    if not package_source.exists():
        errors.append(f"gateway catkin package source is missing: {package_source}")
    for rel_path in ("package.xml", "CMakeLists.txt", "srv/TaskCommandJson.srv"):
        if not (package_source / rel_path).exists():
            errors.append(f"gateway catkin package missing {rel_path}")
    return errors


def _remove_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _next_commands(*, repo_root: Path, catkin_src: Path) -> List[str]:
    workspace = catkin_src.parent
    return [
        f"cd {workspace}",
        "catkin_make",
        "source devel/setup.bash",
        f"PYTHONPATH={repo_root}:$PYTHONPATH python3 - <<'PY'\nfrom platform_gateway_msgs.srv import TaskCommandJson\nprint(TaskCommandJson)\nPY",
        f"PYTHONPATH={repo_root}:$PYTHONPATH python3 {repo_root / 'tools/run_ros1_platform_gateway_node.py'} --platform-id uav_0 --platform-type uav --capability inspect_area --capability relay_or_overwatch --service-symbol {SERVICE_SYMBOL}",
    ]
