"""通信端点的读写函数：动作名保持 auto-<方法名>（工作站代理按方法名绑定），并带前端显示名。"""

from pathlib import Path

import workstation_demo

PACKAGE_DIR = Path(workstation_demo.__file__).resolve().parent


def test_endpoint_actions_keep_auto_names_and_have_display_names():
    from unilabos.registry.registry import Registry

    registry = Registry()
    registry.setup(devices_dirs=[str(PACKAGE_DIR)], complete_registry=True, external_only=True)
    expected = {
        "serial_mock": {"auto-send_command": "发送指令", "auto-read_data": "读取应答"},
        "io_mock_modbus": {"auto-write_io_coil": "写线圈", "auto-read_io_coil": "读线圈"},
    }
    for device_id, names in expected.items():
        actions = registry.device_type_registry[device_id]["class"]["action_value_mappings"]
        assert {name: actions[name]["display_name"] for name in actions} == names, (device_id, sorted(actions))
