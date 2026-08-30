from __future__ import annotations

from workstation_demo.smoke import (
    assert_smoke_proof,
    assert_workflow_proof,
    run_smoke,
)


def test_real_workstation_hostlink_smoke() -> None:
    proof = run_smoke("hostlink", timeout=40.0)
    # 阶段一：共享串口 + Modbus slave_id 注入闭环
    assert_smoke_proof(proof, "hostlink")
    # 阶段二：默认子工作流已上报，可通过管理 API 检索、运行并全部成功
    assert_workflow_proof(proof["workflow"])
