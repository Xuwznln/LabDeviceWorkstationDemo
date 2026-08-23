from __future__ import annotations

from workstation_demo.smoke import run_smoke


def test_real_workstation_hostlink_smoke() -> None:
    proof = run_smoke("hostlink", timeout=20.0)

    assert proof["serial"] == {
        "success": True,
        "command": "PING",
        "response": "PONG",
    }
    assert proof["modbus_sensor_a"]["slave_id"] == 3
    assert proof["modbus_sensor_a"]["result"] == {
        "slave_id": 3,
        "coil": 0,
        "value": 1,
    }
    assert proof["modbus_sensor_b"]["slave_id"] == 7
    assert proof["modbus_sensor_b"]["result"] == {
        "slave_id": 7,
        "coil": 2,
        "value": 1,
    }
    assert proof["shared_serial_endpoint"] == "serial_mock"
    assert proof["shared_modbus_endpoint"] == "io_mock_modbus"
