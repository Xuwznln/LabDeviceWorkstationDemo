"""工作站 demo 默认子工作流：串口回环 + 双 Modbus 传感器探测。

host 启动时由主仓 AST 扫描发现本模块（@workflow），import 后按稳定 uuid
幂等上报到本机 Workflow Authority，前端/HTTP 可直接引用运行。

寻址方式对照：
- ``ctx.run_template("demo_workstation/run_demo")``：demo_workstation 类在图中
  只有一个实例（DemoWorkstation），构建时自动填充 device_id，无需确认；
- ``ctx.run("modbus_sensor_a/probe")``：modbus_sensor 类有 A/B 两个实例，
  必须显式指定 device_id（run_template 会因歧义报错）。

三步分属三个设备且无连线，可并发调度；断言只看各自返回值。
"""

from unilabos.registry.workflows import WorkflowBuildContext, workflow

#: smoke/测试按显示名检索上报结果，保持单一出处。
DEMO_PIPELINE_WORKFLOW_NAME = "工作站演示流水"


@workflow(
    display_name=DEMO_PIPELINE_WORKFLOW_NAME,
    description="共享串口回环（类名自动解析单实例）+ 双 Modbus 传感器探测（显式实例）",
    tags=["workstation-demo", "shared-endpoint"],
)
def demo_pipeline(ctx: WorkflowBuildContext) -> None:
    """单实例类走 run_template 自动填充；多实例类显式 ctx.run。"""

    ctx.run_template("demo_workstation/run_demo", {"cmd": "PING"}, name="串口回环")
    ctx.run("modbus_sensor_a/probe", {"coil": 0, "value": 1}, name="传感器A探测")
    ctx.run("modbus_sensor_b/probe", {"coil": 2, "value": 1}, name="传感器B探测")
