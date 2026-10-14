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

1. Ru1确认ECS为feature/frontend-backend-alignment、41e3f15（grafted浅克隆）；
   本地验证该commit是发布分支祖先。必须显式fetch新snapshot分支，旧分支git pull不会取得新快照实现。
   不自动切换或重启，先检查工作树和数据库准备情况。
2. 先备份并在测试库演练back/migrations/002_gait_snapshot_v1.sql，再更新/重启B。
   它新增7张派生表和触发器，MySQL DDL隐式提交，不能当成可事务回滚脚本。
3. 核对已有六临床表/38字段；001_raw_data_per_foot.sql假设空表，已有数据不能直接重跑。
   不向已有RDS导入整个database_schema_mysql.sql，不用db.create_all代替正式迁移。
4. B身份需原始数据读取及派生表/审计相应权限；纯SELECT账号不能创建快照。
5. 部署后再实际验证医生登录、患者/会话、ensure/full/status与压力/IMU，保留采集接口回归。
6. Agent真实患者模型限制不因B发布而解除；本次不把真实数据发给模型。

发布到原snapshot分支供fetch/检视，不擅自切换ECS分支、合并main或force push。

## 41e3f15到新版本的额外身份结构前置核对

实际models/schema差异：旧Clinician有terminal_code NOT NULL，唯一键为
(phone,terminal_code)；新模型去掉terminal_code，唯一键为(hospital,phone)。
002快照迁移不处理这个差异，目前migrations目录只有001原始字段和002快照脚本。
不能由服务器commit推断RDS一定仍是旧结构，也不能直接断言002已覆盖所有升级。
若旧非空字段仍在，新医生注册可能失败；若医院/手机号有重复组，新登录唯一身份可能冲突。
只做结构/聚合数量检查，不读取或导出患者/医生个人明细，不自行合并身份或删除字段。

可由Ru1在DMS执行只读检查并提供结果（不含数据明细/密码）：

```sql
SHOW CREATE TABLE clinicians;
SELECT COUNT(*) AS duplicate_identity_groups
FROM (SELECT hospital, phone FROM clinicians
      GROUP BY hospital, phone HAVING COUNT(*) > 1) AS conflicts;
```

先确定实际表结构、重复组和已有账号保留策略，再独立设计身份迁移；本次不生成或执行
未确认的身份DDL。不得导入包含DROP TABLE的database_schema_mysql.sql。
