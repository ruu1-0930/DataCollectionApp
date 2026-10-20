# GPS06 E03：固定隔离 MySQL 验收

本资产只供 Ru1 在 ECS 手动执行。固定库为 `lanya_gps_verify_20261020`，产品源码基线
`c00dcfd916f6af1eb47536363a55786bf4b664c9`；发布时由控制任务给出新增 helper 的完整提交 SHA。
本地辅助测试通过不表示 MySQL/RDS 已通过。生产 `lanya` 无 GPS 表，当前业务仍运行旧版，
本操作不 pull、不重启服务、不迁移生产库、不安装依赖、不初始化 MySQL。

2026-10-21实际回执：Ru1运行固定helper `266bd5af2e8b6c631649cb0635723ed512dde57e`，
preflight、service全项、15项约束拒绝、retry/stop真实LOCK WAIT及服务READ COMMITTED、七表清理全部通过，
末行`MYSQL_GPS_VERIFY_OK`。此页保留复现/审计入口，不要求重复已通过验证。
锁阶段0.14/0.10秒不是性能基准；生产迁移/服务/APK/真机仍待验。Ru1选择先部署做单设备短时联调，
规模GPS GET耗时与内存检查在部署后、正式放量前执行，不静默删除该项。

## 运行前提

测试库已经由 Ru1 建好：`clinicians/patients/devices/device_raw_data` 只有结构，
005 的 `collection_sessions/collection_insole_frames/collection_gps_raw` 在同一测试库。
七表必须全部为空且为 InnoDB。脚本拒绝任何其他库、缺表、多表、非空或非 MySQL 8 服务。
不复制生产患者、账号、raw 或 PII。合成账号口令不可登录；不创建 `patient_pii`、派生表或模型数据。

沿用 `/opt/DataCollectionApp/back/.env` 中 DB_HOST、DB_PORT（缺省 3306）、DB_USER、DB_PASS；
只读取指定文件，不 `source`，不采用 DB_NAME/SECRET_KEY，不打印连接串或异常详情。
使用现有 `/opt/DataCollectionApp/back/venv/bin/python`（目标 ECS Python 3.10.12），不改正在运行的进程环境。
helper 以 Python 3.10 为目标；本地辅助测试在 Windows Python 3.12，实际ECS运行成功回执见页首，解释器版本以ECS打印为准。
历史 `157702c` 通过service后在约束阶段失败；固定`266bd5a`按精确errno处理真实PyMySQL的3819 OperationalError，
Ru1随后已实跑至约束/锁全部通过。实际旧列精度仍为collected_at DATETIME(3)、uploaded_at DATETIME，不因验收改变。

除了测试库已有访问权，锁等待观察需要已有账号能读取 `information_schema.innodb_trx`，
并看见这次脚本自身的 writer/contender 事务（MySQL 常要求 PROCESS 可见性）。
不可见、无权限或超时都会 FAIL；不得为了让脚本通过而执行 GRANT、改白名单、重置凭据、修改 SSL 或绕过检查。
请先回报失败阶段，由控制任务决定后续边界。

## 固定提交导出后执行

等待控制任务完成补推，并拿到其核验过的完整 helper SHA，再执行以下一整个块。
把第一行占位符替换成回执中的 **40 位 SHA**；不要使用分支名、HEAD 或产品旧 SHA 代替。
脚本所在提交同时包含产品基线 back/ 源码。此块只在子 shell 内切换到独立 `mktemp` 目录，
保留当前业务进程 cwd/env；factory 可能创建的 `uploads/` 也只落在该临时目录。

```bash
(
  set -eu
  gps_verify_commit='REPLACE_WITH_CONTROLLER_VERIFIED_FULL_HELPER_SHA'
  case "$gps_verify_commit" in *[!0-9a-f]*|'') printf '%s\n' 'Invalid fixed helper SHA'; exit 1;; esac
  test "${#gps_verify_commit}" -eq 40
  test "$(git -C /opt/DataCollectionApp rev-parse "$gps_verify_commit^{commit}")" = "$gps_verify_commit"
  git -C /opt/DataCollectionApp merge-base --is-ancestor c00dcfd916f6af1eb47536363a55786bf4b664c9 "$gps_verify_commit"
  if git -C /opt/DataCollectionApp ls-tree -r --name-only "$gps_verify_commit" -- back/ | grep -Eq '(^|/)\.env$'; then
    printf '%s\n' 'Refusing archive with tracked .env'; exit 1
  fi
  gps_verify_tmp="$(mktemp -d /tmp/gps-mysql-verify.XXXXXXXX)"
  git -C /opt/DataCollectionApp archive "$gps_verify_commit" back/ | tar -x -C "$gps_verify_tmp"
  test -f "$gps_verify_tmp/back/tools/verify_collection_gps_mysql.py"
  cd "$gps_verify_tmp"
  printf 'Helper commit: %s\nWorkspace: %s\n' "$gps_verify_commit" "$gps_verify_tmp"
  /opt/DataCollectionApp/back/venv/bin/python --version
  /opt/DataCollectionApp/back/venv/bin/python back/tools/verify_collection_gps_mysql.py --env-file /opt/DataCollectionApp/back/.env
)
```

若 ECS 尚未 fetch 到 helper 提交，`rev-parse` 会提前停止；不要临时 pull 或更换 SHA。
由控制任务提供已授权的 fetch 步骤。本块不自动删除临时目录，也不删除测试库，方便检查。
数据库成功清理只删本轮合成行；自增计数不回退。

## 检查与回执

按顺序检查 `OK` 阶段，最终退出码必须为 0 且末行必须是 `MYSQL_GPS_VERIFY_OK`。
只有全部业务、锁等待、约束和清理都通过才打印此标记。出现 FAIL、Python/依赖错误、超时或没有标记，
均保留“实库验收待完成”，不要重跑去覆盖失败；先回报完整的简短阶段输出，不贴 `.env`、口令、URL 或原始 GPS。
FAIL 可附 `checkpoint=静态名称, category=受限类别, helper_line=本脚本行号`；真实 DBAPI 错误可另含安全整数 `mysql_errno`，用来定位检查位置；
不会输出异常全文、任意异常类型名、SQL参数、原始载荷或凭据。回报这些简短诊断即可。

该程序实际调用当前源码 `create_capture/ingest_batch/stop_capture`，保留原 Session/commit/rollback。
工厂注册旧路由时会无条件加载/训练 SVM，因此仅在独立验收进程中以 fail-fast `api.analysis.analyze` 哨兵
阻止那次无关导入；若任何路径试图推理，立即失败，不伪造推理结果。没有模型运行或 HTTP 服务。

通过范围：

- 合成医生/患者/设备与三次 capture 提交后对独立 service Session 可见；create 重试幂等。
- 38 字段拆为真实 L/R raw 与 sidecar，GPS1 原始 13 列保持独立；accepted/duplicate 回执时间相同。
- 两流同 key 改载荷返回 409 且不增行；先新事件再冲突的整批回滚；停止同值幂等、闭区间补传及窗外拒绝。
- 跨日手机毫秒时间、GPS UTC 原文本与旧服务器 raw 时钟独立；五个 GPS DOUBLE 精度回读。
  `insole.raw_clock` 只读核对原表两列精度与当前 `@@SESSION.sql_mode`，以 sidecar 服务器时间加八小时为源，
  分别精确比较毫秒 collected 与秒 uploaded；默认半秒向上舍入、`TIME_TRUNCATE_FRACTIONAL` 截断，
  包括跨秒/跨日进位，无一秒公差或 CAST 等同 INSERT 假设。参见 [MySQL 小数秒规则](https://dev.mysql.com/doc/refman/8.0/en/fractional-seconds.html)。
  DOUBLE 存储使用同一核验连接、固定列和本轮 GPS id 的原始 driver SELECT 严格等值检查，
  不放宽公差；另校验 ORM 结果符合真实 model processor。MySQL DOUBLE 默认 `asdecimal=True`，
  ORM 视图会转为十位小数 Decimal，这种读值转换不能冒称数据库丢失精度；产品模型不改。
- 15 次真实约束拒绝，分别覆盖新三表七个 FK、两个 CHECK、六个非主键 UNIQUE；每次回滚。
  各案例只接受对应精确错误码 1062/1452/3819；权限错误、未知/缺失/非整数错误码或 UPDATE 成功都失败。
  不依赖 IntegrityError 子类名称判定 CHECK，其他 DBAPIError 也不会一概通过；实际拒绝证据与 DMS metadata 标记分开。
- 两个实际 InnoDB 交错：writer 的真实 ingest flush 后、commit 前持有 capture 锁；
  contender 的真实 account read 后尝试 capture FOR UPDATE，观察其事务进入 LOCK WAIT 后放行 writer；
  5000ms 样本提交后 exact retry 返回 duplicate；另一 capture 的 4000ms stop 等待后返回 409。
  READ COMMITTED 取自两个实际 service Session 所绑定的 DBAPI 连接，不用 observer 的默认隔离级别冒充。
- 无任意睡眠制造顺序：Event 与真实 SQLAlchemy 执行/提交事件协调，observer 仅有界轮询锁元数据。
  总共最多两个 worker 与一个 observer；等待、连接及 socket 读写均有超时。超时也会释放屏障、join 并失败。
- finally 在同一固定库核验合成标识及归属，再按 GPS→sidecar→capture→raw→device→patient→clinician
  逐个精确 ID 清理；七表全部为空才成功。有活动 worker 时拒绝清理，未知行/清理失败也不会成功。

回报 helper 完整 SHA、ECS Python 版本、退出码与全部 OK/FAIL 行即可。
本验收不证明生产迁移、ECS 新版本服务运行、真实 BLE/APK、设备对时、GPS 精度或实际规模性能。
锁阶段秒数仅是该小样本验收耗时，不是吞吐量或生产延迟指标。
