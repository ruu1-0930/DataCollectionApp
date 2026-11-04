# 派生质量 V2 写版本配置

D03/D04 联合交付增加 HTTP 工厂配置 `GAIT_SNAPSHOT_SCHEMA_VERSION`，默认文本 `1`，配置模板保持1。值 `2` 将新快照／投影配对为2，analyzer 为 `snapshot-pipeline-v3`。非法值在应用启动时拒绝，避免延迟为请求失败。只影响新 ensure 的版本身份，历史原文不重写。无 SQL 迁移。

先更新支持 V2 的 A Agent 与工作台，确认联合版本，再由 Ru1 在 B 的运行环境启用2并重启；当前没有 push／部署或改动私密配置。A 的交付与进度见同名 feature 工作树 `docs/agent-v2/derived-quality-runtime-delivery-2026-11-04.md`。退回1后历史V2仍需新消费者读取，不能把应用降为只认V1的版本。

验证仅本地临时 SQLite／合成数据：新测试四项有效 RED（V2配置未生效、三非法配置未拒绝），实现后集中三文件87passed/1新夹具字段名错误/447既有 warnings；纠正 full/projection 的不同版本字段及诊断 version=1 后，新文件5passed/12既有warnings/2.59s。旧API和V2其余用例未变，不重复矩阵。未运行RDS、ECS3.10或设备，未碰用户uni-app/manifest.json。

在本树使用 `D:/ME5001/runtime/gps-backend-dev/.venv/Scripts/python.exe`，`PYTHONPATH` 指向 `back`，TEMP/TMP 指向 Git 外可写目录：

```powershell
python -m pytest -p no:cacheprovider back/tests/test_snapshot_schema_configuration.py -q --tb=line --basetemp <new-temp>
```

5 passed表示默认／显式V2正式HTTP／启动配置检查通过；不代表MySQL或生产验收。B本地实现提交63f441f4d41010ed57d018dfe9d2357a0365c89b，随后独立进度提交；最终整块审查未发现B问题，A的一项静态source诊断Schema Minor由A修复。未push，manifest不在提交内。
