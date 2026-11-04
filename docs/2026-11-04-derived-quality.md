# 派生质量输入计数模块：D01

新增 `back/services/gait_derivation_quality.py::analyze_derivation_quality(frames)`，输入为既有冻结配对帧结构，输出version=1的四项诊断。只返回事实，不过滤、不改数值、不影响现有质量门禁，尚未接线到SnapshotPipeline、工作台或Agent。

每个比值指标包含total_frames、formula_input_count、excluded_frame_count、exclusions、observations和state。前两种数量满足input+excluded=total；exclusions中的missing_operand/zero_denominator/non_finite_result互斥。非有限原始字段沿用聚合函数的缺失操作数语义，前置已置空的字段不伪装成已知原始原因。

observations与公式输入可重叠：negative_source_frames统计所需字段中含有限负值的帧；incomplete_bilateral_fields统计所需左右字段有缺失/非有限值的帧。它们不是被排除的数量。周期额外记录nonpositive_period_frames；当前公式仍可能产生零或负周期，诊断不静默删除。

周期state在实际输入少于2时为insufficient_variation_inputs，其他时候available；available只表示有限的逐帧公式输入存在（周期至少2个），不保证最终聚合值存在，也不证明行走条件或临床可信。极端有限输入在均值/方差聚合时仍可能溢出；最终值是否存在须读取既有聚合结果。近零分母不擅设阈值，CV不裁到100%。其他比值指标输入0时unavailable。

不对称性用左右独立会话均值，formula_input_count为可形成的均值比较数0或1，不是帧数；另有left_input_count/right_input_count/paired_input_count及comparison_exclusions。即使paired=0，也可能通过独立均值完成比较，诊断明确保留这个事实。

验证：新测试先因模块不存在而RED。首次实现集中1failed/43passed；溢出夹具双侧1e308导致操作数均值先溢出，实际missing_operand，未达到测试想覆盖的分母求和溢出。改为单侧有限1e308操作数、分母相加溢出后保留原non_finite_result断言。最后两文件47passed/0.15s。

复现：在B根目录，设置PYTHONPATH为back、TEMP/TMP为可写Git外runtime，然后用现有后端虚拟环境python执行：

```text
python -m pytest -p no:cacheprovider back/tests/test_gait_derivation_quality.py back/tests/test_gait_analysis.py -q --tb=line --basetemp D:/ME5001/runtime/workbench-remediation-temp/derived-count-reproduce-new
```

测试覆盖单输入CV与最终汇总n区别、停走零值混合、精确零分母、近零分母保留、缺失/非有限、负值平均、交错来源、左右无重叠窗口、非正周期及溢出；与既有公式/聚合statistics.n对照，输入不变。仅本地纯函数/旧算法回归，无外部模型、数据库或设备调用。后端虚拟环境实际Python3.14，不等同ECS Python3.10验收；模块使用3.10支持语法，但本轮未在3.10运行。

后续D02–04应版本化快照/投影、页面中英阅读、Agent上下文及门禁；不得将本模块独立通过记成端到端完成。当前用户uni-app manifest改动保持原样，无push/部署/迁移。

独立限域审查0 Critical / 0 Important / 1 Minor：计数/守恒/观察口径通过；Minor为available可能被读作最终CV可用。源码docstring与本文已澄清，不改计算。复核者一次纯函数探针确认两帧单侧step_length=5e307、walking_speed=1时input_count=2，但旧聚合最终CV=None；此处只记录输入群体，不重复计算CV。原47项结果不因文案修改重跑，也不加总审查探针为通过率。
