from __future__ import annotations

from workstation_demo.smoke import assert_workflow_proof, run_smoke


def test_real_workstation_hostlink_smoke() -> None:
    proof = run_smoke("hostlink", timeout=60.0)
    # 设备不自跑任何动作：共享串口回环、A/B 传感器 slave_id 注入、共享端点计数
    # 全部由默认子工作流经管理 API 触发并从节点结果断言
    assert_workflow_proof(proof["workflow"], "hostlink")
