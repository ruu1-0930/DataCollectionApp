# B 快照/工作台发布清单（2026-10-14）

Ru1授权整理已有实现并push，随后自行更新ECS；RDS尚未完成快照表迁移。
本轮不连接服务器/RDS、不执行迁移、不改生产配置、不合并main。

## GitHub与本地版本

fetch确认origin/main=93d6f12，origin/feature/frontend-backend-alignment=7cbdf1e。
原snapshot本地分支refactor/sarcogait-snapshot-v1=a469550，尚无同名远端分支。
main相对snapshot另有5个合并节点；snapshot有57个main未包含提交，含已实现临床
查询/鉴权改进及revision/pipeline/storage/API，不是57个未经验证新功能。
本轮保留历史，只补齐压力/IMU snapshot-pipeline-v2的既有未提交增量。

## 本次固定内容

- 三个service：snapshot_contracts/pipeline/repository共用snapshot-pipeline-v2。
- SnapshotV1既有chart三字段：左右足九点ADC均值（含零）、双侧加速度模长均值。
- 缺点/非有限/负值/无法表示留null；不混角速度，最多前500帧。
- 新版本ensure生成新identity，旧快照/报告不回填；schema仍V1。
- sensor chart与service的新旧版本回归、原AGENTS/架构中的D21实现记录。

## 实际验证

```powershell
$env:PYTHONPATH='D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1\back\.test-deps'
& 'D:\ME5001\DataCollectionApp\back\venv\Scripts\python.exe' -B -X utf8 -m pytest -p no:cacheprovider back/tests/test_snapshot_sensor_charts.py back/tests/test_snapshot_pipeline.py back/tests/test_snapshot_repository.py back/tests/test_analysis_snapshot_service.py -q
```

103 passed/227 warnings，13.57s，exit0。warning为既有SQLAlchemy utcnow和sklearn
SVC probability弃用提示。当前venv直接满足此集中检查；未安装/修改依赖。
仅合成SQLite，不是MySQL/RDS或生产验收；不重跑Lead基线/复杂授权矩阵。
`git diff --check`通过。最终实现commit与推送结果在同目录进度记录。

## ECS/RDS前置条件

1. ECS当前分支与commit尚待用户提供，不把origin/main当成已部署版本。
2. 先备份并在测试库演练back/migrations/002_gait_snapshot_v1.sql，再更新/重启B。
   它新增7张派生表和触发器，MySQL DDL隐式提交，不能当成可事务回滚脚本。
3. 核对已有六临床表/38字段；001_raw_data_per_foot.sql假设空表，已有数据不能直接重跑。
   不向已有RDS导入整个database_schema_mysql.sql，不用db.create_all代替正式迁移。
4. B身份需原始数据读取及派生表/审计相应权限；纯SELECT账号不能创建快照。
5. 部署后再实际验证医生登录、患者/会话、ensure/full/status与压力/IMU，保留采集接口回归。
6. Agent真实患者模型限制不因B发布而解除；本次不把真实数据发给模型。

发布到原snapshot分支供fetch/检视，不擅自切换ECS分支、合并main或force push。
