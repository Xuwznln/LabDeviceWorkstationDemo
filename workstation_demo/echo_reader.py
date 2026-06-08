"""回显读取设备 — 通过 hardware_interface 代理复用工作站内的串口。

本设备自身不直接持有串口。它在 ``__init__`` 中把 ``self.hardware_interface``
设为某个通信设备的 id 字符串 (例如 ``"serial_mock"``)。工作站启动时，
``ROS2WorkstationNode`` 会检测到该字符串指向一个已注册的通信子设备，并把本设备的
``send_command`` / ``read_data`` 方法替换 (代理) 为通信设备的实现。

代理建立的条件 (见 ``unilabos/ros/nodes/presets/workstation.py``)：
1. 设备 driver 实例上存在 ``hardware_interface`` 属性 (= 通信设备 id 字符串)；
2. 存在 ``send_command`` (write) 与 ``read_data`` (read) 方法；
3. ``hardware_interface`` 的值正好是同工作站内某个子设备的 id。
"""

import logging
from typing import Any, Dict, Optional

from unilabos.registry.decorators import (
    HardwareInterface,
    action,
    device,
    not_action,
    topic_config,
)


@device(
    id="echo_reader",
    category=["sensor"],
    description="回显读取设备 — 通过共享串口 (hardware_interface 代理) 收发指令",
    displayname="回显读取设备",
    hardware_interface=HardwareInterface(
        name="hardware_interface",
        read="read_data",
        write="send_command",
    ),
)
class EchoReaderDevice:
    """演示通过共享串口收发指令的设备。"""

    def __init__(
        self,
        device_id: Optional[str] = None,
        port: str = "serial_mock",
        **kwargs: Any,
    ) -> None:
        """初始化回显读取设备。

        Args:
            device_id[设备ID]: 设备实例 ID，默认 echo_reader。
            port[通信设备ID]: 指向同工作站内通信设备的 id (如 serial_mock)；
                工作站启动后会据此把读写方法代理到该通信设备。
        """
        self.device_id = device_id or "echo_reader"
        # name="hardware_interface" => 工作站用这个属性的值定位通信设备
        self.hardware_interface = port
        self.logger = logging.getLogger(f"EchoReaderDevice.{self.device_id}")
        self._last_command: str = ""
        self._last_response: str = ""

    def post_init(self, ros_node: Any) -> None:
        self._ros_node = ros_node

    @not_action
    def send_command(self, command: str) -> str:
        """默认写实现 (未接入工作站代理时的兜底)；接入后被替换为通信设备实现。"""
        self.logger.warning("[EchoReader] 未接入通信代理，send_command 返回空串")
        return ""

    @not_action
    def read_data(self) -> str:
        """默认读实现 (未接入工作站代理时的兜底)；接入后被替换为通信设备实现。"""
        return ""

    @action(description="发送指令并读取应答")
    def query(self, cmd: str = "PING") -> Dict[str, Any]:
        """通过共享串口发送一条指令并返回应答。

        注意：形参名用 ``cmd`` 而非 ``command``——本地 job/add 接口会把 ``action_args``
        里名为 ``command`` 的键特殊拆包成裸字符串，导致经 ``_execute_driver_command``
        通道转发时报错。经该通道调用的动作请避开保留键 ``command``。

        Args:
            cmd[指令]: 要发送的 ASCII 指令，例如 PING / ID? / STATUS?。
        """
        response = self.send_command(cmd)
        self._last_command = cmd
        self._last_response = response
        return {"success": True, "command": cmd, "response": response}

    @property
    @topic_config()
    def last_response(self) -> str:
        """最近一次读取到的应答。"""
        return self._last_response
