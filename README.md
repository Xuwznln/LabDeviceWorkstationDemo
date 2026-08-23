# UniLabOS Workstation Demo

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

The repository CI also runs the registry scan, HostLink pytest smoke, and ROS2
smoke against a pinned Uni-Lab-OS revision.

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

## Workflow and HTTP boundary

The obsolete `POST /api/v1/job/add` endpoint is not used. In a deployed system,
submit definitions and runs to the Backend Workflow Authority:

- `POST /api/v1/workflows` creates a workflow definition;
- `PUT /api/v1/workflows/{uuid}/graph` stores its canonical graph;
- `POST /api/v1/workflow-tasks` starts one run;
- `GET /api/v1/workflow-tasks/{uuid}` and
  `GET /api/v1/workflow-tasks/{uuid}/jobs` read terminal state and node jobs.

The default Edge microbackend intentionally does not mount this Workflow
Authority. A same-origin gateway should route the workflow paths above to the
Backend Authority and runtime/materials/telemetry/history paths to the Edge.
`control.v1` WebSocket messages are UUID/cursor invalidation notices only; the
Edge fetches command and workflow bodies over typed HTTP before executing them.

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
