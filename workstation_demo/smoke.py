"""有限时启动真实工作站图并验证共享串口、Modbus 注入和动作返回。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _stop(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _base_command(
    repo_root: Path,
    database_root: Path,
    management_port: int,
    backend: str,
) -> list[str]:
    import unilabos

    config_path = (
        Path(unilabos.__file__).resolve().parent
        / "config"
        / "example_config.py"
    )
    command = [
        sys.executable,
        "-m",
        "unilabos",
        "--backend",
        backend,
        "--skip_env_check",
        "--devices",
        str(repo_root / "workstation_demo"),
        "--external_devices_only",
        "--visual",
        "disable",
        "--disable_browser",
        "--port",
        str(management_port),
        "--server_database_root",
        str(database_root),
        "--working_dir",
        str(database_root / "work"),
        "--config",
        str(config_path),
        "-g",
        str(repo_root / "graph" / "workstation_demo.json"),
    ]
    if backend == "ros2":
        command.append("--disable_hostlink")
    return command


def run_smoke(
    backend: str = "hostlink",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """启动同一份 graph，等待驱动写出终态证明后主动停止进程。"""

    if backend not in {"hostlink", "ros2"}:
        raise ValueError("backend must be hostlink or ros2")
    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix=f"workstation-demo-{backend}-"
    ) as directory:
        root = Path(directory)
        proof_path = root / "proof.json"
        log_path = root / "runtime.log"
        environment = os.environ.copy()
        environment.update(
            {
                "WORKSTATION_DEMO_PROOF_FILE": str(proof_path),
                "WORKSTATION_DEMO_START_DELAY": (
                    "2.0" if backend == "ros2" else "0.2"
                ),
                "PYTHONUNBUFFERED": "1",
            }
        )
        hostlink_port = _free_port()
        command = _base_command(
            repo_root,
            root / "db",
            _free_port(),
            backend,
        )
        if backend == "hostlink":
            command += [
                "--hostlink_bind",
                "127.0.0.1",
                "--hostlink_port",
                str(hostlink_port),
            ]
        else:
            domain_id = str(10 + hostlink_port % 190)
            environment["ROS_DOMAIN_ID"] = domain_id
            command += ["--ros_domain_id", domain_id]

        with log_path.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                command,
                cwd=repo_root,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if proof_path.is_file():
                        proof = json.loads(
                            proof_path.read_text(encoding="utf-8")
                        )
                        if proof.get("success") is not True:
                            raise RuntimeError(
                                f"{backend} smoke failed: {proof}\n"
                                + log_path.read_text(
                                    encoding="utf-8", errors="replace"
                                )
                            )
                        if proof.get("backend") != backend:
                            raise RuntimeError(
                                f"unexpected backend proof: {proof}"
                            )
                        return proof
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                raise RuntimeError(
                    f"{backend} smoke did not complete within {timeout}s\n"
                    + log_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            finally:
                _stop(process)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("hostlink", "ros2"),
        default="hostlink",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_smoke(args.backend, args.timeout),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
