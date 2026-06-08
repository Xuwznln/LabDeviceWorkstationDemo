"""模拟串口设备 — 工作站内的串口通信端点 (communication device)。

本设备扮演 "通信端点" 角色：它不连接真实串口，而是用内存字典模拟一个会
应答指令的下位机。同一工作站内的其它子设备通过 hardware_interface 代理机制，
把自身的 send_command / read_data 方法替换为本设备的实现，从而实现
"多个设备共享同一个串口"。

约束：设备节点的 id 必须以 ``serial_`` (或 ``io_``) 开头，
``ROS2WorkstationNode`` 才会把它识别为通信设备并参与代理替换。
"""

import logging
from typing import Any, Dict, List, Optional

from unilabos.registry.decorators import device, topic_config


# 通信端点无需声明 hardware_interface：方法名 send_command(写)/read_data(读) 正好是
# 框架默认值 (见 unilabos/ros/initialize_device.py)，使用方代理时会据此定位本设备的读写函数。
@device(
    id="serial_mock",
    category=["communication_devices"],
    description="模拟串口设备 — 内存模拟读写，供工作站内其它设备共享",
    displayname="模拟串口",
)
class MockSerialDevice:
    """内存模拟串口：写入一条指令即返回模拟应答，读取返回最近一次应答。"""

    _RESPONSES = {
        "PING": "PONG",
        "ID?": "MOCK-SERIAL-v1",
        "STATUS?": "OK",
        "VERSION?": "1.0.0",
    }

    def __init__(
        self,
        device_id: Optional[str] = None,
        port: str = "MOCK1",
        baudrate: int = 9600,
        **kwargs: Any,
    ) -> None:
        """初始化模拟串口设备。

        Args:
            device_id[设备ID]: 设备实例 ID，默认 serial_mock。
            port[端口号]: 模拟端口名，仅用于展示，不连接真实硬件。
            baudrate[波特率]: 模拟波特率，仅用于展示。
        """
        self.device_id = device_id or "serial_mock"
        self.port = port
        self.baudrate = baudrate
        # 端点自身不指向任何上游通信设备，置 None 以保证工站不会反过来代理本设备
        self.hardware_interface = None
        self.logger = logging.getLogger(f"MockSerialDevice.{self.device_id}")
        self._last_response: str = ""
        self._history: List[Dict[str, str]] = []

    def post_init(self, ros_node: Any) -> None:
        self._ros_node = ros_node

    def send_command(self, command: str) -> str:
        """模拟 "写"：发送一条指令并返回模拟下位机应答。

        Args:
            command[指令]: 要发送给模拟下位机的 ASCII 指令。
        """
        cmd = (command or "").strip()
        response = self._RESPONSES.get(cmd.upper(), f"ECHO:{cmd}")
        self._last_response = response
        self._history.append({"command": cmd, "response": response})
        self.logger.info(f"[MockSerial] {cmd} -> {response}")
        return response

    def read_data(self) -> str:
        """模拟 "读"：返回最近一次指令对应的模拟应答。"""
        return self._last_response

    @property
    @topic_config()
    def last_response(self) -> str:
        """最近一次模拟应答。"""
        return self._last_response

    @property
    @topic_config()
    def command_count(self) -> int:
        """已处理的模拟指令总数。"""
        return len(self._history)
