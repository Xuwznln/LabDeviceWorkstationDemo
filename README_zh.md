# device_package_workstation_demo

[English](README.md) | **中文**

Uni-Lab-OS 外部设备包示例，演示 **`hardware_interface` 代理**：同一工作站内的多个子设备共享
同一个通信端点。包含**两种模式**：

- **B1 — 共享串口**：多个设备共享同一个（模拟）串口。
- **B2 — `extra_info` 注入（Modbus slave_id）**：多个传感器共享同一条（模拟）Modbus 总线，
  每个传感器在每次读写时自动带上各自的 `slave_id`。

## 包含的设备

| 设备 class        | 类                | 模式 | 角色                                                              |
| ----------------- | ----------------- | ---- | ----------------------------------------------------------------- |
| `serial_mock`     | `MockSerialDevice`| B1   | 模拟串口端点（内存模拟读写），用默认方法名 `send_command`/`read_data` |
| `echo_reader`     | `EchoReaderDevice`| B1   | 使用方设备，其 `send_command`/`read_data` 被代理到 `serial_mock` |
| `io_mock_modbus`  | `MockModbusBus`   | B2   | 模拟 Modbus 端点，使用**自定义**方法名 `write_io_coil`/`read_io_coil` |
| `modbus_sensor`   | `ModbusSensor`    | B2   | 共享总线的使用方，声明 `extra_info=["slave_id"]`，每次调用自动注入自身 `slave_id` |
| `demo_workstation`| `DemoWorkstation` | —    | 组合上述全部子设备的工作站，提供 `run_demo` 动作                 |

## 前置条件

```bash
mamba activate unilab          # ROS 2 (humble) + unilabos 环境
cd <repo-root>                 # 所有命令均在 Uni-Lab-OS 仓库根目录执行
```

> **凭据是必填的。** `unilabos.app.main` 在未提供 `--ak` / `--sk` 时会立即退出（它需要一个云端
> 实验室）。可复用 IDE「test」运行配置里的 AK/SK/addr（或你在 <https://leap-lab.bohrium.com>
> 注册的账号）。`--upload_registry` 是唯一可选的云端参数（用于上报注册表，想更快启动可去掉）。
> **没有完全离线模式**——`--ak/--sk/--addr` 必须始终带上。

---

## 代理工作原理

`ROS2WorkstationNode` 启动子设备时分两轮：

1. **初始化所有子设备**：id 以 `serial_` / `io_` 开头的会被登记为 *通信端点*。
2. **代理替换**：对每个子设备读取其 `_hardware_interface = {name, read, write, extra_info}`：
   - 取 `getattr(driver, name)`（这里 `name="hardware_interface"`）的值；
   - 若该值是字符串且正好等于某个通信端点的 id，则把本设备的 `read` / `write` 方法
     **替换** 为端点对应的方法；
   - 此外，使用方 `extra_info` 里列出的每个名字会在**调用时**从使用方实例上取值，
     并作为关键字参数注入到端点的读写函数（这正是每设备 `slave_id` 随调用携带的原理）。

角色区分：

| 角色       | `hardware_interface.name`                       | `read` / `write`                                        | `extra_info`                       |
| ---------- | ----------------------------------------------- | ------------------------------------------------------- | ---------------------------------- |
| 通信端点   | 设为 `None`（保证自身不被代理）                 | **必须指向自己真实的 IO 方法**（或用默认名 `send_command`/`read_data` 并省略该参数） | 它能接收的 kwargs（如 `slave_id`） |
| 使用方     | 一个保存端点 id 的属性（如 `self.hardware_interface = "serial_mock"`） | 自身上被代理替换掉的方法名                              | 自身上每次调用要注入的属性（如 `["slave_id"]`） |

> **使用非默认方法名的端点【必须】声明 `hardware_interface`。** `serial_mock` 用的是默认名
> （`send_command`/`read_data`）可省略；但 `io_mock_modbus` 用 `write_io_coil`/`read_io_coil`，
> 所以**必须**显式声明——否则代理会回退到默认名 `send_command`/`read_data` 而报
> `AttributeError`。（框架会打印清晰错误并跳过该绑定，而不是让整个工作站崩溃；但在你声明
> 真实方法名之前，该绑定仍不会生效。）
> **代理绑定只依赖 `config`（`port`/端点 id 的取值）匹配，与图的 `links` 无关。** 随包的图
> `"links": []`。

### B1 — 共享串口

- `serial_mock` 暴露 `send_command`(write) / `read_data`(read)，id 以 `serial_` 开头；
- `echo_reader.__init__` 里 `self.hardware_interface = port`，图文件中 `port = "serial_mock"`；
- 启动后 `echo_reader.send_command` / `read_data` 被代理到 `serial_mock`，实现“多个设备共享一个串口”。

### B2 — `extra_info` 注入（Modbus slave_id）

- `io_mock_modbus` 是端点，其 `write_io_coil(coil, value, slave_id=None)` /
  `read_io_coil(coil, slave_id=None)` 接收 `slave_id` 关键字参数；
- `modbus_sensor` 声明 `extra_info=["slave_id"]`，并从图 `config` 设置 `self.slave_id`
  （`modbus_sensor_a` → 3、`modbus_sensor_b` → 7）；
- 被代理的 `write_io_coil` / `read_io_coil` 触发时，工作站会把使用方当前的 `self.slave_id`
  以 `slave_id=<值>` 注入。于是共享同一条总线的两个传感器，各自自动带上自己的从站号。

---

## 启动教学（单进程，自带 `-g` 图文件）

任选一个空闲端口（这里用 `8100`）。端点 id 与代理绑定都来自图的 `config`，无需 `links`。

```bash
python -m unilabos.app.main \
  --devices ./device_package_workstation_demo/workstation_demo \
  --external_devices_only \
  --ak <你的AK> --sk <你的SK> --addr test --upload_registry \
  --disable_browser --port 8100 \
  -g ./device_package_workstation_demo/graph/workstation_demo.json
```

当日志显示五个子设备全部初始化，并出现以下两行时即启动正常：

```
[Uvicorn] Uvicorn running on http://0.0.0.0:8100
[WebSocketClient] Host node ready signal published with 2 devices
```

## 试运行动作（已实测）

动作提交到本地 HTTP 接口 `POST /api/v1/job/add`，请求体为
`{device_id, action, sample_material:{}, action_args:{...}}`。

> ⚠️ **动作参数不要起名 `command`。** `job/add` 接口会把 `action_args.command` 当作"裸指令字符串"
> 拆包，从而破坏经通用 `_execute_driver_command` 通道转发的动作（它们要求 dict）。这正是
> `run_demo` / `query` 用参数名 `cmd` 的原因。

**Windows PowerShell（Invoke-RestMethod）：**

```powershell
$base = "http://127.0.0.1:8100/api/v1/job/add"
function Run-Action($id,$act,$args){ Invoke-RestMethod -Uri $base -Method Post -ContentType "application/json" -Body (@{device_id=$id;action=$act;sample_material=@{};action_args=$args}|ConvertTo-Json -Compress) }

Run-Action "DemoWorkstation" "run_demo" @{ cmd="PING" }      # B1 串口（经工作站）
Run-Action "echo_reader"     "query"    @{ cmd="ID?" }       # B1 串口（直接调使用方）
Run-Action "modbus_sensor_a" "probe"    @{ coil=0; value=1 } # B2 extra_info，slave_id=3
Run-Action "modbus_sensor_b" "probe"    @{ coil=2; value=1 } # B2 extra_info，slave_id=7
```

**Linux/macOS（或 Windows `curl.exe`）：**

```bash
curl -X POST http://127.0.0.1:8100/api/v1/job/add \
  -H "Content-Type: application/json" \
  -d '{"device_id":"modbus_sensor_a","action":"probe","sample_material":{},"action_args":{"coil":0,"value":1}}'
```

每次调用返回 `{"code":0,"data":{"status":1,...}}`（已受理）。真正的结果在服务端日志里：

```
# B1 —— echo_reader 的收发被代理到 serial_mock
[MockSerial] PING -> PONG
[DemoWorkstation] PING -> PONG
[MockSerial] ID? -> MOCK-SERIAL-v1

# B2 —— 每个传感器把自己的 slave_id 注入到共享总线
[MockModbus] WRITE slave=3 coil=0 value=1     # modbus_sensor_a
[MockModbus] READ  slave=3 coil=0 -> 1
[MockModbus] WRITE slave=7 coil=2 value=1     # modbus_sensor_b
[MockModbus] READ  slave=7 coil=2 -> 1
```

来自**同一条** `io_mock_modbus` 总线却出现不同的 `slave=3` / `slave=7`，就是 `extra_info`
把各使用方自身属性注入进去的现场证据。

## 停止

对进程按 `Ctrl+C`（或 kill 对应 PID）。

---

## 本地验证（注册表 check，不启动）

```bash
cd device_package_workstation_demo
unilab --check_mode --devices ./workstation_demo --external_devices_only
```

## 常见问题

- 启动后立刻退出并提示「请前往 … 注册实验室」：`--ak/--sk` 缺失或无效。它们是必填的（见前置条件）。
- `'<端点>' object has no attribute 'send_command'`：通信端点用了自定义方法名却没声明
  `hardware_interface` 的真实 `read`/`write`。补上声明。
- `执行动作时JSON必须为dict`：你给动作起了名为 `command` 的参数（会被拆包）。改名即可（如 `cmd`）。
- 端口被占用：换一个 `--port`。

## 目录结构

```
device_package_workstation_demo/
├── README.md                     # English
├── README_zh.md                  # 中文（本文件）
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── .github/workflows/check_registry.yml
├── graph/
│   └── workstation_demo.json     # 工作站图文件（串口 + modbus 子设备）
└── workstation_demo/             # 被 --devices 扫描的 python 包
    ├── __init__.py
    ├── mock_serial.py            # MockSerialDevice（B1 端点）
    ├── echo_reader.py            # EchoReaderDevice（B1 使用方）
    ├── mock_modbus_bus.py        # MockModbusBus（B2 端点）
    ├── modbus_sensor.py          # ModbusSensor（B2 使用方，extra_info=slave_id）
    └── demo_workstation.py       # DemoWorkstation（工作站）
```
