# device_package_workstation_demo

**English** | [中文](README_zh.md)

An external device package for Uni-Lab-OS that demonstrates the **`hardware_interface` proxy**:
several sub devices inside one workstation share a single communication endpoint. It covers **two
patterns**:

- **B1 — shared serial**: multiple devices share one (mock) serial port.
- **B2 — `extra_info` injection (Modbus slave_id)**: multiple sensors share one (mock) Modbus bus,
  and each one automatically carries its own `slave_id` on every read/write.

## Devices

| Device class      | Class             | Pattern | Role                                                                              |
| ----------------- | ----------------- | ------- | -------------------------------------------------------------------------------- |
| `serial_mock`     | `MockSerialDevice`| B1      | Mock serial endpoint (in-memory read/write), default method names `send_command`/`read_data` |
| `echo_reader`     | `EchoReaderDevice`| B1      | Consumer whose `send_command`/`read_data` are proxied to `serial_mock`            |
| `io_mock_modbus`  | `MockModbusBus`   | B2      | Mock Modbus endpoint with **custom** method names `write_io_coil`/`read_io_coil`  |
| `modbus_sensor`   | `ModbusSensor`    | B2      | Consumer sharing the bus; declares `extra_info=["slave_id"]` so its own `slave_id` is injected on every call |
| `demo_workstation`| `DemoWorkstation` | —       | Workstation composing all of the above; exposes a `run_demo` action               |

## Prerequisites

```bash
mamba activate unilab          # ROS 2 (humble) + unilabos environment
cd <repo-root>                 # run all commands from the Uni-Lab-OS repo root
```

> **Credentials are mandatory.** `unilabos.app.main` exits immediately if `--ak` / `--sk` are not
> provided (it needs a lab on the cloud). Reuse the AK/SK/addr from your IDE "test" run
> configuration (or your own account at <https://leap-lab.bohrium.com>). `--upload_registry` is the
> only optional cloud flag (it pushes the registry; drop it for a faster start). There is **no**
> fully offline mode — `--ak/--sk/--addr` must always be present.

---

## How the proxy works

`ROS2WorkstationNode` starts the sub devices in two passes:

1. **Initialize all sub devices**: ids starting with `serial_` / `io_` are registered as
   *communication endpoints*.
2. **Proxy replacement**: for each sub device it reads its
   `_hardware_interface = {name, read, write, extra_info}`:
   - take the value of `getattr(driver, name)` (here `name="hardware_interface"`);
   - if that value is a string equal to some communication endpoint's id, **replace** this
     device's `read` / `write` methods with the endpoint's implementation;
   - additionally, every name listed in the consumer's `extra_info` is read from the consumer
     instance **at call time** and injected as a keyword argument into the endpoint's read/write
     (this is how per-device `slave_id` rides along).

Key role distinction:

| Role                  | `hardware_interface.name` | `read` / `write`                                  | `extra_info`                          |
| --------------------- | ------------------------- | ------------------------------------------------- | ------------------------------------- |
| Communication endpoint | set to `None` (so it is never proxied) | **must point to its real IO methods** (or use the default names `send_command`/`read_data` and omit the decorator arg) | the kwargs it accepts (e.g. `slave_id`) |
| Consumer              | an attribute holding the endpoint id (e.g. `self.hardware_interface = "serial_mock"`) | the method names on itself that get replaced by the proxy | the attributes on itself to inject each call (e.g. `["slave_id"]`) |

> **Endpoints with non-default method names MUST declare `hardware_interface`.** `serial_mock` uses
> the defaults (`send_command`/`read_data`) so it can omit the arg, but `io_mock_modbus` uses
> `write_io_coil`/`read_io_coil`, so it **must** declare them — otherwise the proxy falls back to
> `send_command`/`read_data` and raises `AttributeError`. (The framework logs a clear error and
> skips that binding instead of crashing the whole workstation, but the binding still won't work
> until you declare the real method names.)
> **Proxy binding depends only on `config` (the `port`/endpoint-id values) matching, not on graph
> `links`.** The shipped graph has `"links": []`.

### B1 — shared serial

- `serial_mock` exposes `send_command` (write) / `read_data` (read), id starts with `serial_`;
- `echo_reader.__init__` sets `self.hardware_interface = port`, and the graph sets `port = "serial_mock"`;
- after startup, `echo_reader.send_command` / `read_data` are proxied to `serial_mock`, realizing
  "multiple devices sharing one serial port".

### B2 — `extra_info` injection (Modbus slave_id)

- `io_mock_modbus` is the endpoint; its `write_io_coil(coil, value, slave_id=None)` /
  `read_io_coil(coil, slave_id=None)` accept a `slave_id` kwarg;
- `modbus_sensor` declares `extra_info=["slave_id"]` and sets `self.slave_id` from the graph
  `config` (`modbus_sensor_a` → 3, `modbus_sensor_b` → 7);
- when the proxied `write_io_coil` / `read_io_coil` fire, the workstation injects the consumer's
  current `self.slave_id` as `slave_id=<value>`. So two sensors sharing one bus each carry their
  own slave id automatically.

---

## Launch tutorial (single process, ships its own `-g` graph)

Pick any free port (here `8100`). The endpoint ids and proxy bindings come from the graph's
`config`; no `links` are needed.

```bash
python -m unilabos.app.main \
  --devices ./device_package_workstation_demo/workstation_demo \
  --external_devices_only \
  --ak <YOUR_AK> --sk <YOUR_SK> --addr test --upload_registry \
  --disable_browser --port 8100 \
  -g ./device_package_workstation_demo/graph/workstation_demo.json
```

Startup is healthy when the log shows all five sub devices initialized and:

```
[Uvicorn] Uvicorn running on http://0.0.0.0:8100
[WebSocketClient] Host node ready signal published with 2 devices
```

## Try the actions (verified)

Actions are submitted to the local HTTP API `POST /api/v1/job/add`. The body is
`{device_id, action, sample_material:{}, action_args:{...}}`.

> ⚠️ **Do not name an action parameter `command`.** The `job/add` endpoint treats an
> `action_args.command` key as a "raw command string" and unwraps it, which breaks actions
> dispatched through the generic `_execute_driver_command` channel (they need a dict). That is why
> `run_demo` / `query` use the parameter name `cmd`.

**Windows PowerShell (Invoke-RestMethod):**

```powershell
$base = "http://127.0.0.1:8100/api/v1/job/add"
function Run-Action($id,$act,$args){ Invoke-RestMethod -Uri $base -Method Post -ContentType "application/json" -Body (@{device_id=$id;action=$act;sample_material=@{};action_args=$args}|ConvertTo-Json -Compress) }

Run-Action "DemoWorkstation" "run_demo" @{ cmd="PING" }      # B1 serial via workstation
Run-Action "echo_reader"     "query"    @{ cmd="ID?" }       # B1 serial via the consumer directly
Run-Action "modbus_sensor_a" "probe"    @{ coil=0; value=1 } # B2 extra_info, slave_id=3
Run-Action "modbus_sensor_b" "probe"    @{ coil=2; value=1 } # B2 extra_info, slave_id=7
```

**Linux/macOS (or Windows `curl.exe`):**

```bash
curl -X POST http://127.0.0.1:8100/api/v1/job/add \
  -H "Content-Type: application/json" \
  -d '{"device_id":"modbus_sensor_a","action":"probe","sample_material":{},"action_args":{"coil":0,"value":1}}'
```

Each call returns `{"code":0,"data":{"status":1,...}}` (accepted). The proof shows up in the
server log:

```
# B1 — echo_reader's send/read proxied to serial_mock
[MockSerial] PING -> PONG
[DemoWorkstation] PING -> PONG
[MockSerial] ID? -> MOCK-SERIAL-v1

# B2 — each sensor injects its own slave_id onto the shared bus
[MockModbus] WRITE slave=3 coil=0 value=1     # modbus_sensor_a
[MockModbus] READ  slave=3 coil=0 -> 1
[MockModbus] WRITE slave=7 coil=2 value=1     # modbus_sensor_b
[MockModbus] READ  slave=7 coil=2 -> 1
```

The differing `slave=3` / `slave=7` from the **same** `io_mock_modbus` bus is the live proof that
`extra_info` injects each consumer's own attribute.

## Stopping

Stop the process with `Ctrl+C` (or kill the PID).

---

## Registry check (validate the package without launching)

```bash
cd device_package_workstation_demo
unilab --check_mode --devices ./workstation_demo --external_devices_only
```

## Troubleshooting

- Process exits right after start with "请前往 ... 注册实验室" / "register a lab": `--ak/--sk` were
  missing or invalid. They are mandatory (see Prerequisites).
- `'<Endpoint>' object has no attribute 'send_command'`: the communication endpoint uses custom
  method names but did not declare `hardware_interface` with the real `read`/`write`. Declare them.
- `执行动作时JSON必须为dict` / `function_args must be a dict`: you passed an action parameter named
  `command` (it gets unwrapped). Rename the parameter (e.g. to `cmd`).
- Port already in use: pick a different `--port`.

## Directory structure

```
device_package_workstation_demo/
├── README.md                     # English (this file)
├── README_zh.md                  # 中文
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── .github/workflows/check_registry.yml
├── graph/
│   └── workstation_demo.json     # workstation graph (serial + modbus sub devices)
└── workstation_demo/             # python package scanned by --devices
    ├── __init__.py
    ├── mock_serial.py            # MockSerialDevice (B1 endpoint)
    ├── echo_reader.py            # EchoReaderDevice (B1 consumer)
    ├── mock_modbus_bus.py        # MockModbusBus (B2 endpoint)
    ├── modbus_sensor.py          # ModbusSensor (B2 consumer, extra_info=slave_id)
    └── demo_workstation.py       # DemoWorkstation (the workstation)
```
