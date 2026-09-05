"""有限时启动真实工作站图，经管理 HTTP API 运行默认子工作流并核对共享端点。

设备启动后不自跑任何动作。host 启动时已把 workstation_demo/workflows.py 里的
@workflow 幂等上报到本机 Workflow Authority；本脚本复现网页操作：

1. ``GET  /api/v1/workflows``              找到「工作站演示流水」；
2. ``POST /api/v1/workflow-tasks``         创建任务（网页"运行"按钮）；
3. ``GET  /api/v1/workflow-tasks/{uuid}``   等终态；
4. ``GET  /api/v1/workflow-tasks/{uuid}/jobs`` 读四步结果：run_demo（类名单实例自动填充）
   经共享串口回环、A/B 传感器探测（显式实例，各自 slave_id 注入共享 Modbus 总线）、
   inspect_endpoints 读出共享端点的累计计数（串口 1 条指令、Modbus 4 次操作 = 两次
   probe 各写 + 读）。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

#: 与 workstation_demo/workflows.py 保持一致（smoke 独立运行，不 import 设备包）。
WORKFLOW_DISPLAY_NAME = "工作站演示流水"


def assert_workflow_proof(workflow_proof: dict[str, Any], backend: str) -> None:
    """断言默认子工作流：任务成功、四步各自返回正确、共享端点计数与两次 probe 一致。"""

    assert workflow_proof["workflow_name"] == WORKFLOW_DISPLAY_NAME
    assert workflow_proof["task_status"] == "succeeded", f"工作流任务未成功: {workflow_proof}"
    jobs = workflow_proof["jobs"]
    assert len(jobs) == 4, f"应有 4 个节点 job: {jobs}"
    assert all(job["status"] == "succeeded" for job in jobs), f"存在失败 job: {jobs}"

    # jobs 按 topological_index 返回；节点 uuid 序 == 声明序
    run_demo_result, sensor_a_result, sensor_b_result, endpoints = [
        job["return_info"]["return_value"] for job in jobs
    ]
    # run_template 单实例自动填充 -> 真实跑通共享串口链路
    assert run_demo_result == {
        "success": True,
        "command": "PING",
        "response": "PONG",
        "status_transition": ["Idle", "Running", "Idle"],
    }, run_demo_result
    # 显式实例 -> 各自 slave_id 被注入到共享总线
    assert sensor_a_result == {
        "success": True,
        "slave_id": 3,
        "result": {"slave_id": 3, "coil": 0, "value": 1},
    }
    assert sensor_b_result == {
        "success": True,
        "slave_id": 7,
        "result": {"slave_id": 7, "coil": 2, "value": 1},
    }
    # 共享端点的累计计数：一条串口指令；两次 probe 各写 + 读 = 4 次 Modbus 操作
    assert endpoints["success"] is True and endpoints["backend"] == backend, endpoints
    assert endpoints["shared_serial_endpoint"] == "serial_mock"
    assert endpoints["shared_modbus_endpoint"] == "io_mock_modbus"
    assert endpoints["workstation_status"] == "Idle"
    assert endpoints["serial_endpoint_state"] == {"last_response": "PONG", "command_count": 1}
    assert endpoints["modbus_endpoint_state"] == {"op_count": 4}
    assert endpoints["sensor_state"] == {"modbus_sensor_a": 1, "modbus_sensor_b": 1}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _stop(process: subprocess.Popen[Any]) -> None:
    """结束 unilab 进程树（权威进程 + 它拉起的 Host 子进程），不留孤儿占着数据库文件。"""

    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _graph_path(repo_root: Path) -> Path:
    """优先读取 wheel 安装的数据文件，editable/source 模式回退到仓库 graph。"""

    installed = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "workstation_demo"
        / "graph"
        / "workstation_demo.json"
    )
    if installed.is_file():
        return installed
    source = repo_root / "graph" / "workstation_demo.json"
    if source.is_file():
        return source
    raise FileNotFoundError("Workstation demo graph 未随 distribution 安装")


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
        str(_graph_path(repo_root)),
    ]
    if backend == "ros2":
        command.append("--disable_hostlink")
    return command


# ---------------------------------------------------------------------------
# 管理 HTTP API（工作流阶段）
# ---------------------------------------------------------------------------


def _api_request(
    port: int, path: str, payload: dict[str, Any] | None = None
) -> dict[str, Any] | list[Any]:
    """请求管理 API 并解包 {"code": 0, "data": ...}；HTTP/业务错误抛异常。"""

    url = f"http://127.0.0.1:{port}/api/v1{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    # GET 不能带 JSON Content-Type：服务端 Backend 路由会尝试解码空 body 而报错
    headers = {} if payload is None else {"Content-Type": "application/json"}
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
    # workflow 风格 {"code":0,"data":...} 自动解包；/health 等直出 DTO 原样返回
    if isinstance(body, dict) and "code" in body and ("data" in body or "error" in body):
        if body["code"] != 0:
            raise RuntimeError(f"管理 API {path} 返回错误: {body}")
        return body.get("data")
    return body


def run_workflow_stage(management_port: int, timeout: float) -> dict[str, Any]:
    """检索上报的默认子工作流 -> 创建任务 -> 等待成功 -> 汇总节点结果。"""

    deadline = time.monotonic() + timeout

    workflow_uuid = ""
    while time.monotonic() < deadline:
        try:
            listing = _api_request(
                management_port, "/workflows?page=1&page_size=50"
            )
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
            continue
        matches = [
            item
            for item in listing["items"]
            if item["name"] == WORKFLOW_DISPLAY_NAME
        ]
        if matches:
            workflow_uuid = matches[0]["uuid"]
            break
        time.sleep(0.3)
    if not workflow_uuid:
        raise RuntimeError(
            f"{timeout}s 内未在管理 API 检索到工作流 {WORKFLOW_DISPLAY_NAME!r}"
        )

    task = _api_request(
        management_port,
        "/workflow-tasks",
        {"workflow_uuid": workflow_uuid, "run_mode": "normal"},
    )
    task_uuid = task["uuid"]

    status = str(task.get("status") or "")
    while time.monotonic() < deadline and status not in {"succeeded", "failed"}:
        time.sleep(0.3)
        current = _api_request(management_port, f"/workflow-tasks/{task_uuid}")
        status = str(current.get("status") or "")
    if status not in {"succeeded", "failed"}:
        raise RuntimeError(f"工作流任务 {task_uuid} 未在 {timeout}s 内结束: {status}")

    jobs = _api_request(management_port, f"/workflow-tasks/{task_uuid}/jobs")
    return {
        "workflow_uuid": workflow_uuid,
        "workflow_name": WORKFLOW_DISPLAY_NAME,
        "task_uuid": task_uuid,
        "task_status": status,
        # task 级 output 不进公开 HTTP 契约，节点结果一律取 job.return_info
        "jobs": [
            {
                "uuid": job["uuid"],
                "status": job["status"],
                "return_info": dict(job.get("return_info") or {}),
            }
            for job in jobs
        ],
    }


def _actions_online(port: int, action_names: set[str]) -> bool:
    """执行端点快照已上报这些动作能力：调度器此刻才能把 job 派发到设备（ROS2 节点起得慢）。"""

    endpoints = _api_request(port, "/runtime/endpoints?state=online&limit=100")
    reported = {
        capability["action_name"]
        for endpoint in endpoints
        for capability in endpoint.get("action_capabilities", [])
        if capability.get("state", "active") == "active"
    }
    return action_names <= reported


def _wait_management_api(port: int, process: subprocess.Popen[Any], deadline: float) -> None:
    """等管理 API 就绪、执行面在线且工作站动作已上报（工作流才能派发到设备）。"""

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("runtime process exited before the management API came up")
        try:
            health = _api_request(port, "/health")
            # 只等工作站自己的动作：子设备动作（probe / query）在 ROS2 下经工作站节点派发，
            # 不单独出现在端点能力表里
            if (
                health.get("status") == "ok"
                and health.get("execution") == "ready"
                and _actions_online(port, {"run_demo", "inspect_endpoints"})
            ):
                return
        except (urllib.error.URLError, OSError, RuntimeError, AttributeError, KeyError, TypeError):
            pass
        time.sleep(0.3)
    raise RuntimeError("管理 API / 设备动作能力未在时限内就绪")


def run_smoke(
    backend: str = "hostlink",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """启动同一份 graph，经管理 API 运行工作流并断言，随后主动停止进程。"""

    if backend not in {"hostlink", "ros2"}:
        raise ValueError("backend must be hostlink or ros2")
    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(
        prefix=f"workstation-demo-{backend}-", ignore_cleanup_errors=True
    ) as directory:
        root = Path(directory)
        log_path = root / "runtime.log"
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        hostlink_port = _free_port()
        management_port = _free_port()
        command = _base_command(
            repo_root,
            root / "db",
            management_port,
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
                try:
                    _wait_management_api(management_port, process, deadline)
                except Exception:
                    sys.stderr.write(
                        "STARTUP FAILED\n" + log_path.read_text(encoding="utf-8", errors="replace") + "\n"
                    )
                    raise
                # 上报已在启动时完成，这里检索并真实运行工作流（设备不自跑任何动作）
                try:
                    workflow = run_workflow_stage(
                        management_port, max(1.0, deadline - time.monotonic())
                    )
                    assert_workflow_proof(workflow, backend)
                except Exception:
                    sys.stderr.write(
                        "WORKFLOW STAGE FAILED\n"
                        + log_path.read_text(encoding="utf-8", errors="replace")
                        + "\n"
                    )
                    raise
                return {"success": True, "backend": backend, "workflow": workflow}
            finally:
                _stop(process)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("hostlink", "ros2"),
        default="hostlink",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
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
