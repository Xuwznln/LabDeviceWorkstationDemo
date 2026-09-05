"""演示工作站 — 组合模拟串口/Modbus 端点与共享它们的使用方设备。

演示要点：
1. 工作站继承 ``WorkstationBase``，由所选 backend 的统一 ``DeviceNode`` 包装；
   驱动本身不依赖 ROS2 API。
2. 子设备通过 hardware_interface 代理共享通信端点：
   - serial_mock (端点) <- echo_reader (使用方，默认方法名)；
   - io_mock_modbus (端点) <- modbus_sensor_a/b (使用方，extra_info 注入 slave_id)。
3. 工作站动作 ``run_demo`` 通过 ``DeviceNode.call_device_action`` 调用 echo_reader，
   串起整条链路：工作站 -> 子设备动作 -> (代理) -> serial_mock；
4. ``inspect_endpoints`` 读出两个共享端点与两台传感器的内部计数，作为「同一端点被
   多个使用方共享」的可断言证据。

设备启动后不自跑任何动作：全部由工作流（``workflows.py``）经管理 API 触发。

注意：config 保留 ``protocol_type`` 字段（本演示用空列表），两种运行时读取同一配置。
"""

import logging
from typing import Any, Dict, List, Optional

from pylabrobot.resources import Deck

from unilabos.devices.workstation.workstation_base import WorkstationBase
from unilabos.backend.runtime.node import DeviceNode
from unilabos.registry.decorators import action, device, not_action, topic_config


@device(
    id="demo_workstation",
    category=["workstation"],
    description="演示工作站 — 共享串口 + 共享 Modbus 总线 (hardware_interface 代理)",
    display_name="演示工作站",
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

    @action(
        display_name="端点状态",
        description="读出共享串口 / 共享 Modbus 端点与两台传感器的内部计数：同一端点被多个使用方共享的证据",
        always_free=True,
    )
    def inspect_endpoints(self) -> Dict[str, Any]:
        """汇报共享端点状态（工作流末步，供断言）。

        串口端点记录最近应答与累计指令数；Modbus 端点记录累计操作数（每次 probe = 写 + 读）；
        两台传感器各记录自己最近读回的值。
        """
        subs = self._device_node.sub_devices
        serial_endpoint = subs["serial_mock"].driver_instance
        modbus_endpoint = subs["io_mock_modbus"].driver_instance
        sensor_a_driver = subs["modbus_sensor_a"].driver_instance
        sensor_b_driver = subs["modbus_sensor_b"].driver_instance
        return {
            "success": True,
            "backend": self._device_node.backend_name,
            "shared_serial_endpoint": "serial_mock",
            "shared_modbus_endpoint": "io_mock_modbus",
            "workstation_status": self.status,
            "serial_endpoint_state": {
                "last_response": serial_endpoint.last_response,
                "command_count": serial_endpoint.command_count,
            },
            "modbus_endpoint_state": {"op_count": modbus_endpoint.op_count},
            "sensor_state": {
                "modbus_sensor_a": sensor_a_driver.last_value,
                "modbus_sensor_b": sensor_b_driver.last_value,
            },
        }

    @property
    @topic_config()
    def status(self) -> str:
        """工作站状态。"""
        return self._status
