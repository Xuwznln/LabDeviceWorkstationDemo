# UniLabOS 工作站演示

[English](README.md) | **中文**

这个外部设备包用同一份工作站图同时演示 `hostlink` 与 `ros2`。五个子设备共享两个通信端点：

- `echo_reader` 复用 `serial_mock`，发送 `PING` 返回 `PONG`；
- `modbus_sensor_a` 与 `modbus_sensor_b` 复用同一个 `io_mock_modbus`，但
  `extra_info=["slave_id"]` 会在每次调用时分别注入从站号 `3` 和 `7`；
- `demo_workstation.run_demo` 使用运行时无关的
  `DeviceNode.call_device_action`，驱动不直接调用 ROS API。

## 从 GitHub 安装

Uni-Lab-OS 支持普通 GitHub 仓库链接和可选的固定 ref：

```bash
unilab package install https://github.com/Xuwznln/LabDeviceWorkstationDemo --ref <commit-sha>
```

本地开发可使用：

```bash
git clone https://github.com/Xuwznln/LabDeviceWorkstationDemo.git
cd LabDeviceWorkstationDemo
python -m pip install -e .
```

本地演示不需要 AK/SK，也不依赖云端实验室。

## 有终止条件的双运行时 smoke

以下两条命令读取完全相同的 `graph/workstation_demo.json`，执行真实设备动作，写出终态
JSON 后自动关闭运行时：

```bash
python -m workstation_demo.smoke --backend hostlink --timeout 30
python -m workstation_demo.smoke --backend ros2 --timeout 60
```

终态证明会断言串口动作返回 `PONG`，并断言同一条 Modbus 总线分别收到
`slave_id=3` 与 `slave_id=7`，不是依靠无限运行日志人工判断。CI 会通过普通 GitHub URL
加当前精确提交 SHA 安装本仓库，切到 checkout 之外的临时目录，在同一个 Jazzy job 中执行
注册表扫描、HostLink 和 ROS2 smoke。每天北京时间 08:00 检查 Uni-Lab-OS `dev`，仅在
出现新 SHA 时重跑；失败的 SHA 次日继续重试。

## 手动启动

在本仓库根目录选择任一 backend：

```bash
python -m unilabos --backend hostlink --skip_env_check \
  --devices ./workstation_demo --external_devices_only \
  --visual disable --disable_browser \
  -g ./graph/workstation_demo.json

python -m unilabos --backend ros2 --disable_hostlink --skip_env_check \
  --devices ./workstation_demo --external_devices_only \
  --visual disable --disable_browser \
  -g ./graph/workstation_demo.json
```

## `hardware_interface` 约定

所选工作站运行节点先初始化全部子设备，再把使用方声明的读写方法绑定到
`hardware_interface` 属性指向的通信端点。`extra_info` 中的字段会在调用时从使用方实例
读取并注入端点调用，所以两个 Modbus 使用方虽共享总线，仍会分别带上从站号 3 和 7。

使用非默认方法名的端点必须显式声明方法。`serial_mock` 使用默认的
`send_command`/`read_data`；`io_mock_modbus` 声明
`write_io_coil`/`read_io_coil`。绑定取决于图中 `config` 的端点 ID，不依赖图的 links。

## 默认子工作流与 HTTP 边界

`workstation_demo/workflows.py` 用主仓的 `@workflow` 装饰器声明了「工作站演示流水」，
对照演示两种寻址方式：

- `ctx.run_template("demo_workstation/run_demo")`：该设备类在图中只有一个实例，
  构建时自动填充 device_id，无需确认；
- `ctx.run("modbus_sensor_a/probe")` / `ctx.run("modbus_sensor_b/probe")`：
  `modbus_sensor` 类有两个实例，必须显式指定实例。

host 启动时 AST 扫描发现该模块，按函数相对路径派生稳定 uuid 幂等上报到本机
Workflow Authority。smoke 的阶段二通过管理 HTTP API 检索并真实运行它：

- `GET /api/v1/workflows` 按显示名检索上报结果；
- `POST /api/v1/workflow-tasks` 创建一次运行（`{"workflow_uuid": ..., "run_mode": "normal"}`）；
- `GET /api/v1/workflow-tasks/{uuid}` 与
  `GET /api/v1/workflow-tasks/{uuid}/jobs` 读取终态和每个节点 job 的 `return_info`。

三个节点分属三个设备且无连线，可并发调度；断言只校验各自返回值
（串口回环 `PONG`、总线分别注入 `slave_id=3/7`）。旧 `POST /api/v1/job/add` 不再使用。

## 目录

```text
graph/workstation_demo.json       两种 backend 共用的一份图
workstation_demo/
  demo_workstation.py             运行时无关的工作站动作
  mock_serial.py / echo_reader.py 共享串口端点与使用方
  mock_modbus_bus.py               共享 Modbus 端点
  modbus_sensor.py                 自动注入 slave_id 的使用方
  smoke.py                         有终止条件的真实运行时证明
tests/test_hostlink_smoke.py       HostLink 集成断言
```
