"""演示工作站 — 组合模拟串口/Modbus 端点与共享它们的使用方设备。

演示要点：
1. 工作站继承 ``WorkstationBase``，``init_wrapper`` 会自动用
   ``ROS2WorkstationNode`` 包装 (无需手写 ROS 节点)。
2. 子设备通过 hardware_interface 代理共享通信端点：
   - serial_mock (端点) <- echo_reader (使用方，默认方法名)；
   - io_mock_modbus (端点) <- modbus_sensor_a/b (使用方，extra_info 注入 slave_id)。
3. 工作站动作 ``run_demo`` 通过 ``self._ros_node.sub_devices`` 访问 echo_reader
   并触发一次收发，串起整条链路：工作站 -> echo_reader -> (代理) -> serial_mock。

注意：config 必须包含 ``protocol_type`` 字段 (本演示用空列表)，因为
``ROS2WorkstationNode`` 会读取 ``driver_params["protocol_type"]``。
"""

import logging
from typing import Any, Dict, List, Optional

from pylabrobot.resources import Deck

from unilabos.devices.workstation.workstation_base import WorkstationBase
from unilabos.registry.decorators import action, device, not_action, topic_config


@device(
    id="demo_workstation",
    category=["workstation"],
    description="演示工作站 — 共享串口 + 共享 Modbus 总线 (hardware_interface 代理)",
    displayname="演示工作站",
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
    def post_init(self, ros_node) -> None:
        super().post_init(ros_node)
        self._ros_node = ros_node

    @not_action
    def get_reader(self):
        """获取 echo_reader 子设备的 driver 实例。"""
        sub = self._ros_node.sub_devices.get("echo_reader")
        if sub is None:
            raise RuntimeError("子设备 echo_reader 未初始化")
        return sub.driver_instance

    @action(description="通过共享串口发送指令并返回应答")
    def run_demo(self, cmd: str = "PING") -> Dict[str, Any]:
        """触发 echo_reader 通过共享的模拟串口收发一条指令。

        注意：形参名用 ``cmd`` 而非 ``command``——因为本地 job/add 接口会把
        ``action_args`` 里名为 ``command`` 的键当作"裸指令字符串"特殊拆包，导致经
        ``_execute_driver_command`` 通道转发时 function_args 不再是 dict 而报错。
        给经该通道调用的动作命名参数时，请避开保留键 ``command``。

        Args:
            cmd[指令]: 要发送的 ASCII 指令，例如 PING / ID? / STATUS?。
        """
        self._status = "Running"
        try:
            reader = self.get_reader()
            response = reader.send_command(cmd)
        finally:
            self._status = "Idle"
        self.logger.info(f"[DemoWorkstation] {cmd} -> {response}")
        return {"success": True, "command": cmd, "response": response}

    @property
    @topic_config()
    def status(self) -> str:
        """工作站状态。"""
        return self._status
