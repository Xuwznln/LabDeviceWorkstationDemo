"""Modbus 传感器 — 演示用 extra_info 注入每设备固有的 slave_id。

本设备通过 hardware_interface 代理复用 ``io_mock_modbus`` 总线；它在 ``extra_info``
里声明 ``["slave_id"]``。工作站在转发 ``read_io_coil`` / ``write_io_coil`` 时，会自动把
本实例的 ``self.slave_id`` 以 ``slave_id=<值>`` 注入给总线的读写函数——因此同一条总线
上的多个传感器即使共享端点，也能各自带上不同的从站号。

对比 ``echo_reader``：echo_reader 用默认方法名 (send_command/read_data) 且不需要额外
参数；本设备用自定义方法名 (read_io_coil/write_io_coil) 且需要注入 slave_id，所以必须
显式声明 ``HardwareInterface``。
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
    id="modbus_sensor",
    category=["sensor"],
    description="Modbus 传感器 — 通过共享总线 + extra_info(slave_id) 收发",
    displayname="Modbus传感器",
    hardware_interface=HardwareInterface(
        name="hardware_interface",
        read="read_io_coil",
        write="write_io_coil",
        extra_info=["slave_id"],  # 关键：把 self.slave_id 随每次读写注入给总线
    ),
)
class ModbusSensor:
    """演示通过共享 Modbus 总线、并自动携带自身 slave_id 的设备。"""

    def __init__(
        self,
        device_id: Optional[str] = None,
        port: str = "io_mock_modbus",
        slave_id: int = 1,
        **kwargs: Any,
    ) -> None:
        """初始化 Modbus 传感器。

        Args:
            device_id[设备ID]: 设备实例 ID，默认 modbus_sensor。
            port[通信设备ID]: 指向同工作站内通信设备的 id (如 io_mock_modbus)。
            slave_id[从站地址]: 本设备的 Modbus 从站号；经 extra_info 注入给总线读写。
        """
        self.device_id = device_id or "modbus_sensor"
        # name="hardware_interface" => 工作站用这个属性的值定位通信设备
        self.hardware_interface = port
        # extra_info=["slave_id"] => 工作站转发读写时会自动带上该属性的值
        self.slave_id = slave_id
        self.logger = logging.getLogger(f"ModbusSensor.{self.device_id}")
        self._last_value: int = 0

    def post_init(self, ros_node: Any) -> None:
        self._ros_node = ros_node

    @not_action
    def write_io_coil(self, coil: int, value: int) -> Dict[str, Any]:
        """默认写实现 (未接入工作站代理时的兜底)；接入后被替换为总线实现并自动带 slave_id。"""
        self.logger.warning("[ModbusSensor] 未接入通信代理，write_io_coil 空操作")
        return {}

    @not_action
    def read_io_coil(self, coil: int) -> Dict[str, Any]:
        """默认读实现 (未接入工作站代理时的兜底)；接入后被替换为总线实现并自动带 slave_id。"""
        return {}

    @action(description="写一个线圈再读回，返回总线应答(含自动注入的 slave_id)")
    def probe(self, coil: int = 0, value: int = 1) -> Dict[str, Any]:
        """演示：写线圈 -> 读线圈。返回里能看到本设备 slave_id 被自动带到了总线。

        Args:
            coil[线圈地址]: 要操作的线圈编号。
            value[线圈值]: 写入值 (0/1)。
        """
        # 下面两次调用经代理后实际是 bus.write/read_io_coil(..., slave_id=self.slave_id)
        self.write_io_coil(coil, value)
        result = self.read_io_coil(coil)
        self._last_value = int(result.get("value", 0)) if isinstance(result, dict) else 0
        return {"success": True, "slave_id": self.slave_id, "result": result}

    @property
    @topic_config()
    def last_value(self) -> int:
        """最近一次读到的线圈值。"""
        return self._last_value
