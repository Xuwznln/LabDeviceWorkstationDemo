"""演示工作站 — 组合模拟串口/Modbus 端点与共享它们的使用方设备。

演示要点：
1. 工作站继承 ``WorkstationBase``，由所选 backend 的统一 ``DeviceNode`` 包装；
   驱动本身不依赖 ROS2 API。
2. 子设备通过 hardware_interface 代理共享通信端点：
   - serial_mock (端点) <- echo_reader (使用方，默认方法名)；
   - io_mock_modbus (端点) <- modbus_sensor_a/b (使用方，extra_info 注入 slave_id)。
3. 工作站动作 ``run_demo`` 通过 ``DeviceNode.call_device_action`` 调用 echo_reader，
   串起整条链路：工作站 -> 子设备动作 -> (代理) -> serial_mock。

注意：config 保留 ``protocol_type`` 字段（本演示用空列表），两种运行时读取同一配置。
"""

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional

from pylabrobot.resources import Deck

from unilabos.devices.workstation.workstation_base import WorkstationBase
from unilabos.backend.runtime.node import DeviceNode
from unilabos.registry.decorators import action, device, not_action, topic_config


@device(
    id="demo_workstation",
    category=["workstation"],
    description="演示工作站 — 共享串口 + 共享 Modbus 总线 (hardware_interface 代理)",
    displayname="演示工作站",
    supported_backends=["hostlink", "ros2"],
)
class DemoWorkstation(WorkstationBase):
    """组合模拟通信端点与共享它们的使用方设备的演示工作站。"""

    def __init__(
        self,
        deck: Optional[Deck] = None,
        protocol_type: Optional[List[str]] = None,
        children: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> None:
        """初始化演示工作站。

        Args:
            deck[台面]: 工作站台面，本演示不使用，保持 None。
            protocol_type[协议类型]: ROS Action 协议名列表，本演示为空列表。
        """
        super().__init__(deck=deck, **kwargs)
        self.protocol_type = protocol_type or []
        self.logger = logging.getLogger("DemoWorkstation")
        self._status = "Idle"

    @not_action
    def post_init(self, device_node: DeviceNode) -> None:
        super().post_init(device_node)
        self._device_node = device_node
        proof_file = os.environ.get("WORKSTATION_DEMO_PROOF_FILE")
        if proof_file:
            threading.Thread(
                target=self._write_smoke_proof,
                args=(Path(proof_file),),
                name="workstation-demo-proof",
                daemon=True,
            ).start()

    @not_action
    def get_reader(self):
        """获取 echo_reader 子设备的 driver 实例。"""
        sub = self._device_node.sub_devices.get("echo_reader")
        if sub is None:
            raise RuntimeError("子设备 echo_reader 未初始化")
        return sub.driver_instance

    @action(display_name="运行串口演示", description="通过共享串口发送指令并返回应答")
    def run_demo(self, cmd: str = "PING") -> Dict[str, Any]:
        """触发 echo_reader 通过共享的模拟串口收发一条指令。

        Args:
            cmd[指令]: 要发送的 ASCII 指令，例如 PING / ID? / STATUS?。
        """
        status_before = self._status
        self._status = "Running"
        status_during = self._status
        try:
            result = self._device_node.call_device_action(
                "echo_reader",
                "query",
                {"cmd": cmd},
                timeout=15.0,
            )
            response = result["response"]
        finally:
            self._status = "Idle"
        self.logger.info(f"[DemoWorkstation] {cmd} -> {response}")
        return {
            "success": True,
            "command": cmd,
            "response": response,
            "status_transition": [status_before, status_during, self._status],
        }

    @not_action
    def _write_smoke_proof(self, proof_file: Path) -> None:
        """在真实运行时中执行有限次动作，并原子写出可机读终态。"""

        delay = float(os.environ.get("WORKSTATION_DEMO_START_DELAY", "1.0"))
        time.sleep(max(0.0, delay))
        try:
            serial = self.run_demo("PING")
            sensor_a = self._device_node.call_device_action(
                "modbus_sensor_a",
                "probe",
                {"coil": 0, "value": 1},
                timeout=15.0,
            )
            sensor_b = self._device_node.call_device_action(
                "modbus_sensor_b",
                "probe",
                {"coil": 2, "value": 1},
                timeout=15.0,
            )
            serial_endpoint = self._device_node.sub_devices["serial_mock"].driver_instance
            modbus_endpoint = self._device_node.sub_devices["io_mock_modbus"].driver_instance
            sensor_a_driver = self._device_node.sub_devices["modbus_sensor_a"].driver_instance
            sensor_b_driver = self._device_node.sub_devices["modbus_sensor_b"].driver_instance
            proof = {
                "success": True,
                "backend": self._device_node.backend_name,
                "serial": serial,
                "modbus_sensor_a": sensor_a,
                "modbus_sensor_b": sensor_b,
                "shared_serial_endpoint": "serial_mock",
                "shared_modbus_endpoint": "io_mock_modbus",
                "workstation_status": self.status,
                "serial_endpoint_state": {
                    "last_response": serial_endpoint.last_response,
                    "command_count": serial_endpoint.command_count,
                },
                "modbus_endpoint_state": {
                    "op_count": modbus_endpoint.op_count,
                },
                "sensor_state": {
                    "modbus_sensor_a": sensor_a_driver.last_value,
                    "modbus_sensor_b": sensor_b_driver.last_value,
                },
            }
        except Exception as exc:  # pragma: no cover - 子进程 smoke 会报告完整错误
            self.logger.exception("工作站 smoke 执行失败")
            proof = {
                "success": False,
                "backend": self._device_node.backend_name,
                "error": f"{type(exc).__name__}: {exc}",
            }
        proof_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = proof_file.with_suffix(proof_file.suffix + ".tmp")
        temporary.write_text(
            json.dumps(proof, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(proof_file)

    @property
    @topic_config()
    def status(self) -> str:
        """工作站状态。"""
        return self._status
