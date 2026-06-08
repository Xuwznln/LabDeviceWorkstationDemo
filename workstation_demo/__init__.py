"""Workstation hardware_interface demo — external device package for Uni-Lab-OS.

演示一个工作站内多个子设备通过 ``hardware_interface`` 代理共享同一通信端点，包含两种模式：

B1) 共享串口（默认方法名）：
    - MockSerialDevice (serial_mock): 模拟串口通信端点 (内存模拟读写)，用默认方法名
      send_command/read_data；
    - EchoReaderDevice (echo_reader): 通过 hardware_interface 代理复用上面的模拟串口。

B2) extra_info 注入每设备固有参数（Modbus slave_id）：
    - MockModbusBus (io_mock_modbus): 模拟 Modbus 总线通信端点，用自定义方法名
      write_io_coil/read_io_coil；
    - ModbusSensor (modbus_sensor): 通过代理复用总线，并用 extra_info=["slave_id"]
      在每次读写时自动注入自身 slave_id (图文件里 A=3 / B=7 两个实例共享同一条总线)。

DemoWorkstation (demo_workstation): 组合上述所有子设备的工作站，提供 run_demo 动作。
"""
