# Uni-Lab-OS Workstation Demo

**English** | [中文](README_zh.md)

This external Uni-Lab-OS package demonstrates one workstation graph on both
`hostlink` and `ros2`. Five sub-devices share two communication endpoints:

- `echo_reader` uses the `serial_mock` endpoint and returns `PONG` for `PING`;
- `modbus_sensor_a` and `modbus_sensor_b` use one `io_mock_modbus` bus while
  `extra_info=["slave_id"]` injects their own addresses (`3` and `7`) on every
  call;
- `demo_workstation.run_demo` uses the backend-neutral
  `DeviceNode.call_device_action` contract. Driver code does not call ROS APIs.

## Install from GitHub

Uni-Lab-OS accepts an ordinary GitHub repository URL and an optional pinned ref:

```bash
unilab package install https://github.com/Xuwznln/LabDeviceWorkstationDemo --ref <commit-sha>
```

For local development:

```bash
git clone https://github.com/Xuwznln/LabDeviceWorkstationDemo.git
cd LabDeviceWorkstationDemo
python -m pip install -e .
```

No AK/SK or cloud laboratory is required for the local demo.

## Deterministic dual-backend smoke

Both commands load the same `graph/workstation_demo.json`, execute real device
actions, write a terminal proof JSON, and stop the runtime automatically:

```bash
python -m workstation_demo.smoke --backend hostlink --timeout 30
python -m workstation_demo.smoke --backend ros2 --timeout 60
```

The proof checks all of the following, rather than relying on an endless log:

```json
{
  "success": true,
  "backend": "hostlink",
  "serial": {"success": true, "command": "PING", "response": "PONG"},
  "modbus_sensor_a": {"slave_id": 3, "result": {"slave_id": 3, "coil": 0, "value": 1}},
  "modbus_sensor_b": {"slave_id": 7, "result": {"slave_id": 7, "coil": 2, "value": 1}}
}
```

CI installs this repository through the ordinary GitHub URL plus the exact commit SHA, changes
to a directory outside the checkout, and runs the registry scan plus both smoke commands in one
Jazzy job. A scheduled run checks Uni-Lab-OS `dev` at 08:00 Beijing time each day and only repeats
the full smoke when that branch has a new SHA (failed SHAs are retried).

## Manual launch

From this repository root, select either backend:

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

## Hardware-interface contract

The selected workstation runtime initializes every child and then binds a
consumer's declared read/write methods to the endpoint named by its
`hardware_interface` attribute. Values in `extra_info` are read from the
consumer at call time and injected into the endpoint call. Therefore the two
Modbus consumers share one bus but still produce `slave_id=3` and `slave_id=7`.

Endpoints using non-default method names must declare them explicitly.
`serial_mock` uses the defaults `send_command`/`read_data`; `io_mock_modbus`
declares `write_io_coil`/`read_io_coil`. The binding is driven by graph `config`
values, not graph links.

## Default sub-workflow and HTTP boundary

`workstation_demo/workflows.py` declares the "工作站演示流水" workflow with the
core `@workflow` decorator, contrasting the two addressing modes:

- `ctx.run_template("demo_workstation/run_demo")`: this device class has exactly
  one instance in the graph, so the device_id is auto-filled at build time;
- `ctx.run("modbus_sensor_a/probe")` / `ctx.run("modbus_sensor_b/probe")`: the
  `modbus_sensor` class has two instances, so explicit instance ids are required.

On host startup the AST scan discovers the module and the definition is
upserted into the local Workflow Authority under a stable uuid derived from the
function path. Stage two of the smoke locates and really runs it over the
management HTTP API:

- `GET /api/v1/workflows` finds the reported definition by display name;
- `POST /api/v1/workflow-tasks` starts one run (`{"workflow_uuid": ..., "run_mode": "normal"}`);
- `GET /api/v1/workflow-tasks/{uuid}` and
  `GET /api/v1/workflow-tasks/{uuid}/jobs` read terminal state and each node
  job's `return_info`.

Declarative `@workflow` steps run strictly serially: each node's
`execution_policy.depends_on` points at the previous step and the scheduler
turns it into DAG dependency edges. Assertions only check each returned value
(serial loopback `PONG`, bus-level `slave_id=3/7` injection). The obsolete
`POST /api/v1/job/add` is not used.

## Package layout

```text
graph/workstation_demo.json       one graph for both backends
workstation_demo/
  demo_workstation.py             backend-neutral workstation action
  mock_serial.py / echo_reader.py shared serial endpoint + consumer
  mock_modbus_bus.py               shared Modbus endpoint
  modbus_sensor.py                 consumers with slave_id injection
  smoke.py                         bounded real-runtime proof
tests/test_hostlink_smoke.py       HostLink integration assertion
```
