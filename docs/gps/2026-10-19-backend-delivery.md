# GPS01 B 后端交付记录

日期：2026-10-19。实现基准：`refactor/sarcogait-snapshot-v1@0d25362`。
权威契约：A `5f1b956` 的 `docs/superpowers/specs/2026-10-19-sarcogait-gps-design.md`，执行对应 GPS01 brief。
本记录只证明本地隔离交付，不代表 MySQL/RDS、ECS、真机 BLE 或生产验收。

## 已实现

- 新增 `collection_sessions`、`collection_insole_frames`、`collection_gps_raw`；采集固定医护、患者、设备和手机开始时刻。
- 三个 POST：create、单流 1–100 事件 batch、stop。精确字段、UUID、安全整数、UTC 毫秒字符串、正文 128 KiB 上限和重复 JSON key 校验。
- 每帧保留原 38 个命名值并拆成原始 L/R 两行，sidecar 引用精确 raw ID；新链路不调用 `analyze`，不写遗留 transformed。
- 新 raw 仍使用真实服务器 UTC+08 naive 摄取时刻；手机接收与服务器 UTC 时刻分列，不用 GPS UTC 校验窗口，不制造递增服务器时间。
- 独立 Session 事务：SQLite `BEGIN IMMEDIATE`，MySQL collection 行 `FOR UPDATE`。事件 ID 与 `(capture,stream,epoch,sequence)` 双唯一；规范内容一致才返回 duplicate，冲突整批回滚。
- stop 与 batch 走同一锁；拒绝早于开始或早于已有样本的停止时间，同值 stop 幂等；停止后接受窗口内缓存补传，拒绝窗口外事件。
- GPS 严格 13 列解析，保存原行和全部字段；fix0、空可选数值、空 UTC 保留，数值非有限/非法文本拒绝。GPS浮点列在 MySQL 明确为 DOUBLE，避免纬经度被默认 FLOAT 缩减精度。
- `GET /patients/{patient_id}/gait/sessions/{session_id}/gps` 沿临床读取范围：医生本人患者，admin 可全量；写入仍仅 clinician。沿既有 Response，安全错误不回传输入或内部异常。
- 旧 gait raw 范围→sidecar→capture/epoch/连续 sequence 的手机窗口；缺号、倒退断 slice。多 slice 稳定排序、首包含归属、sample ID 去重、合并分页，不扩整 capture。
- 质量 `gps-display-v1`：HDOP 3/5/6、age3500、卫星4、fix/坐标范围；无效保留但无轨迹，跨 slice/epoch、间隔>5000ms、手机倒退、异常跳点>60m/s断段。质量与 segment 在全 slice 上生成后分页。
- 最近帧只在归属 slice 内、绝对误差≤1000ms；等距取较早时间、再稳定 ID。左右鞋垫速度来自 sidecar 的 raw IDs，GPS速度独立。
- 严格 `gps-session-v1` JSON Schema；旧记录无 sidecar 返回 unassociated，有 sidecar 无GPS返回 empty。
- 独立 additive `005_collection_gps.sql` 与绿场schema镜像；没有回填旧 raw 或更改 snapshot/Agent/报告代码。

## 文件

新增：`back/api/collection.py`、`back/services/collection_ingest.py`、`back/services/gps_query.py`、`back/contracts/collection_gps_v1.schema.json`、`back/migrations/005_collection_gps.sql`、`back/tests/test_collection_ingest.py`、`back/tests/test_gps_query.py`、`back/tests/test_gps_api.py`、本记录。

修改：`back/models/models.py`、`back/config.py`、`back/database_schema_mysql.sql`。
没有额外 helper 或运行依赖。AGENTS、架构、Plan、统一进度归控制任务维护，不纳入此实现提交。

## 环境与 RED

未重试旧坏 venv launcher。共享工作台 Python3.12 能运行但没有 Flask，未修改其依赖。
以其 base 创建 `D:/ME5001/runtime/gps-backend-dev/.venv`，使用仓库 `back/requirements-dev.txt` 安装专用隔离环境。
实际 Python3.12.14，Flask2.3.3、Flask-SQLAlchemy3.0.5、SQLAlchemy2.1.5、scikit-learn1.9.1、pytest9.1.1、jsonschema4.26.0；`pip check` 为 No broken requirements found。

新增测试先于产品实现。首次运行：

```powershell
Set-Location 'D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1'
& 'D:\ME5001\runtime\gps-backend-dev\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider back/tests/test_collection_ingest.py::test_create_is_idempotent_and_identity_is_frozen -q --disable-warnings
```

结果 `1 failed, 9 warnings in 10.16s`，缺失 POST 路由导致预期200实际404，确认是缺功能。
集中实现后的首轮新增组合 `36 passed, 1 failed`，发现1001ms浮点乘1000再int截断成1000ms；改用 timedelta 整数部分精确计算。
随后 `45 passed, 1 error`，error 为系统临时目录 `pytest-of-Lenovo` 的 WinError5，在并发测试 setup 发生，未执行该项；改为专用 runtime basetemp，没有扩大 ACL 排查。
自审增加手机时钟倒退测试，RED `1 failed` 后修复分段；增加超大 JSON 整数和长gap跳点测试，RED `2 failed, 5 passed` 后修复安全拒绝和跳点检查。

## 最终集中验证

```powershell
Set-Location 'D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1'
& 'D:\ME5001\runtime\gps-backend-dev\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider --basetemp=D:/ME5001/runtime/gps-backend-dev/pytest-gps01-verified back/tests/test_collection_ingest.py back/tests/test_gps_query.py back/tests/test_gps_api.py back/tests/test_raw_data.py back/tests/test_gait_analysis.py::test_segment_pairs_duplicate_timestamp_rows_by_per_foot_ordinal back/tests/test_gait_api.py::test_frames_paginate_duplicate_timestamp_rows_as_logical_frames -q --tb=short
```

实际：`51 passed, 231 warnings in 20.35s`，退出码0。新增测试44项；仅附带旧raw5项与重复帧2项，不重复旧Lead/模型全矩阵。
覆盖同 ID 重试、同序号冲突、整批回滚、stop后窗口内补传、窗口外拒绝、跨owner/admin写拒绝、GPS空/非法数值、固件seq复位、多slice重叠去重与epoch隔离、旧gap裁剪、质量边界、1000/1001ms与等距取早、倒退/跳点断段、无关联/零GPS、严格schema/分页/正文边界。
文件SQLite双线程在独立客户端/Session同时提交同一事件，实际一 accepted、一 duplicate，最终仅两条 raw；新批次用会抛异常的SVM double验证未进入旧analyze。原上传回归仍验证原有行为。
真实 snapshot service 创建快照后插入GPS并查询，断言原 snapshot canonical payload/content_hash/state_version 和 Agent projection canonical payload/hash 原样保留。

231 warnings：既有源文件的 SQLAlchemy utcnow164、JWT utcnow53、旧 Query.get9；专用依赖解析到sklearn1.9后旧SVC概率参数 FutureWarning5。未修改旧模型或为告警扩展测试。

静态/安装验证：三张新表 MySQL dialect DDL 编译通过；005与绿场尾部镜像字节一致；`git diff --check`、`pip check` 通过。

## 边界与后续门禁

- 未运行 MySQL/RDS迁移、InnoDB并发锁/死锁/精度实库测试，SQLite并发不得外推RDS。MySQL5.7忽略CHECK，范围由请求验证，唯一/FK依赖正常启用的数据库约束。
- 005只新增表，不修改旧raw时间列。绿场schema包含DROP，仅用于新建库，严禁导入现有生产库；生产部署前由Ru1在隔离测试库演练005。
- 批量补传仍会压缩旧服务器时间轴；重复时间帧由旧ordinal配对保留，GPS近邻只用sidecar手机时钟，不宣称硬件同步。
- GPS读取为当前最新集合；slice全量派生质量/段后分页，不是固定历史游标。未做生产规模查询性能验收。
- GPS-only记录可保存，但没有独立采集目录；当前GET仍从一个既有gait会话进入。单帧slice是零宽接收点，未匹配到GPS就如实为空，不扩窗或猜最近采集。
- 未访问生产、未使用真实患者、未调用远程模型、未执行ECS操作、未push；App和工作台产品接线尚由后续GPS02/03完成。
