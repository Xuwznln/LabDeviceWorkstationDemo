"""工作站 demo 默认子工作流：串口回环 + 双 Modbus 传感器探测。

host 启动时由主仓 AST 扫描发现本模块（@workflow），import 后按稳定 uuid
幂等上报到本机 Workflow Authority，前端/HTTP 可直接引用运行。

寻址方式对照：
- ``ctx.run_template("demo_workstation/run_demo")``：demo_workstation 类在图中
  只有一个实例（DemoWorkstation），构建时自动填充 device_id，无需确认；
- ``ctx.run("modbus_sensor_a/probe")``：modbus_sensor 类有 A/B 两个实例，
  必须显式指定 device_id（run_template 会因歧义报错）。

四步分属三个设备，按声明序串行执行（execution_policy.depends_on 依赖边）；
末步 ``inspect_endpoints`` 读出共享端点的累计计数，断言只看各自返回值。
设备启动后不自跑任何动作，全部由本工作流经管理 API 触发。
"""

from unilabos.registry.workflows import WorkflowBuildContext, WorkflowGuide, workflow

#: smoke/测试按显示名检索上报结果，保持单一出处。
DEMO_PIPELINE_WORKFLOW_NAME = "工作站演示流水"


@workflow(
    display_name=DEMO_PIPELINE_WORKFLOW_NAME,
    description="共享串口回环（类名自动解析单实例）+ 双 Modbus 传感器探测（显式实例）+ 共享端点计数核对",
    tags=["workstation-demo", "shared-endpoint"],
    guide=WorkflowGuide(
        preparation=[
            "「设备」页确认工作站 DemoWorkstation 及其子设备（serial_mock、echo_reader、io_mock_modbus、modbus_sensor_a/b）在线。",
            "无需准备物料：串口与 Modbus 总线都是内存模拟端点，不连真实硬件。",
            "插入模板时工作站角色（设备类 demo_workstation）单实例自动选中；两台 Modbus 传感器是显式设备 id，多套部署时手选。",
        ],
        expected=[
            "任务 succeeded，四步全部成功。",
            "「串口回环」返回应答 PONG；两次「探测」的返回值里各带自己的 slave_id（由工作站的 hardware_interface extra_info 自动注入）。",
            "「端点状态」里共享串口累计 1 条指令、共享 Modbus 端点累计 4 次操作（每次 probe = 写 + 读），两台传感器各记最近读回的值。",
        ],
        notes=["演示的是同一通信端点被多个使用方共享：读写方法由工作站代理到共享端点，使用方只声明 hardware_interface。"],
    ),
)
def demo_pipeline(ctx: WorkflowBuildContext) -> None:
    """单实例类走 run_template 自动填充；多实例类显式 ctx.run。"""

    ctx.run_template(
        "demo_workstation/run_demo",
        {"cmd": "PING"},
        name="串口回环",
        description="工作站让 echo_reader 经共享模拟串口发送 PING 并返回应答。",
    )
    ctx.run(
        "modbus_sensor_a/probe",
        {"coil": 0, "value": 1},
        name="传感器A探测",
        description="传感器 A 写线圈 0 再读回；总线应答里带 A 自己的 slave_id。",
    )
    ctx.run(
        "modbus_sensor_b/probe",
        {"coil": 2, "value": 1},
        name="传感器B探测",
        description="传感器 B 写线圈 2 再读回；同一条总线、不同 slave_id。",
    )
    ctx.run_template(
        "demo_workstation/inspect_endpoints",
        {},
        name="端点状态",
        description="读出共享串口 / 共享 Modbus 端点的累计计数与两台传感器最近读回的值，供断言。",
    )
