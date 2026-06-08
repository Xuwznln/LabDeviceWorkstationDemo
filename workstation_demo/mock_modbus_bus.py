"""模拟 Modbus 总线 — 演示 hardware_interface 的 extra_info (如 slave_id) 注入。

本设备扮演 "通信端点" 角色 (id 以 ``io_`` 开头)：多个使用方设备共享这一条
"总线"，但各自的 ``slave_id`` 不同。被代理的使用方在转发读写时，工作站会自动把
使用方实例上的 ``slave_id`` 以关键字参数注入到本设备的 ``read_io_coil`` /
``write_io_coil``。因此这两个函数的签名必须带 ``slave_id`` 形参。

与 ``serial_mock`` 一样，本设备不依赖真实硬件，用内存字典模拟线圈状态。
"""

import logging
from typing import Any, Dict, List, Optional

from unilabos.registry.decorators import HardwareInterface, device, topic_config


# 端点用的是【非默认】方法名 (write_io_coil/read_io_coil)，所以【必须】显式声明
# hardware_interface，让工站代理能定位到真正的读写函数；否则会回退到默认名
# send_command/read_data 而报 AttributeError。
@device(
    id="io_mock_modbus",
    category=["communication_devices"],
    description="模拟 Modbus 总线 — 演示 extra_info(slave_id) 注入",
    displayname="模拟Modbus总线",
    hardware_interface=HardwareInterface(
        name="hardware_interface",
        read="read_io_coil",
        write="write_io_coil",
    ),
)
class MockModbusBus:
    """内存模拟 Modbus 总线：按 slave_id 分别维护各自的线圈状态。"""

    def __init__(
        self,
        device_id: Optional[str] = None,
        port: str = "MODBUS1",
        **kwargs: Any,
    ) -> None:
        """初始化模拟 Modbus 总线。

        Args:
            device_id[设备ID]: 设备实例 ID，默认 io_mock_modbus。
            port[端口号]: 模拟端口名，仅用于展示，不连接真实硬件。
        """
        self.device_id = device_id or "io_mock_modbus"
        self.port = port
        # 端点自身不指向任何上游通信设备，置 None 以保证工站不会反过来代理本设备
        self.hardware_interface = None
        self.logger = logging.getLogger(f"MockModbusBus.{self.device_id}")
        # slave_id -> {coil: value}
        self._coils: Dict[int, Dict[int, int]] = {}
        self._history: List[Dict[str, Any]] = []

    def post_init(self, ros_node: Any) -> None:
        self._ros_node = ros_node

    def write_io_coil(self, coil: int, value: int, slave_id: Optional[int] = None) -> Dict[str, Any]:
        """模拟 "写线圈"。``slave_id`` 由工站从使用方的 extra_info 自动注入。

        Args:
            coil[线圈地址]: 线圈编号。
            value[线圈值]: 写入值 (0/1)。
            slave_id[从站地址]: Modbus 从站号；由 extra_info 注入，无需调用方手动传。
        """
        sid = int(slave_id) if slave_id is not None else 0
        self._coils.setdefault(sid, {})[int(coil)] = int(value)
        self._history.append({"op": "write", "slave_id": sid, "coil": int(coil), "value": int(value)})
        self.logger.info(f"[MockModbus] WRITE slave={sid} coil={coil} value={value}")
        return {"slave_id": sid, "coil": int(coil), "value": int(value)}

    def read_io_coil(self, coil: int, slave_id: Optional[int] = None) -> Dict[str, Any]:
        """模拟 "读线圈"。``slave_id`` 由工站从使用方的 extra_info 自动注入。

        Args:
            coil[线圈地址]: 线圈编号。
            slave_id[从站地址]: Modbus 从站号；由 extra_info 注入，无需调用方手动传。
        """
        sid = int(slave_id) if slave_id is not None else 0
        value = self._coils.get(sid, {}).get(int(coil), 0)
        self._history.append({"op": "read", "slave_id": sid, "coil": int(coil), "value": value})
        self.logger.info(f"[MockModbus] READ slave={sid} coil={coil} -> {value}")
        return {"slave_id": sid, "coil": int(coil), "value": value}

    @property
    @topic_config()
    def op_count(self) -> int:
        """已处理的读写操作总数。"""
        return len(self._history)
