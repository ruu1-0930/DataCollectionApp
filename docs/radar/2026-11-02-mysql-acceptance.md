# 室内雷达：限定真实MySQL功能验收回执

2026-11-02，Ru1在ECS手动执行并提供结果；控制者未自行连接数据库。

## 固定范围

- 源码提交：e2384f5bd28d2c9030a3c6ceaab3a54f36921a5c。
- 独立源码目录：/tmp/sarcogait-radar-verify.YGb5Wo76；Python3.10.12，现有venv。
- 固定隔离库：lanya_radar_verify_20261023，MySQL8.0.36；不是生产lanya。
- 前置元数据：9表/9InnoDB/14FK/13非主键UNIQUE/8执行CHECK。
- 命令入口：back/tools/verify_collection_radar_mysql.py --env-file /opt/DataCollectionApp/back/.env；连接字段只在进程内使用，DB_NAME被固定目标覆盖，未回显凭据。

## 实际输出

```text
OK checkpoint=preflight
OK checkpoint=service
OK checkpoint=constraints mysql_errno=1062
OK checkpoint=constraints mysql_errno=1452
OK checkpoint=constraints mysql_errno=3819
OK checkpoint=cleanup
MYSQL_RADAR_VERIFY_OK
```

此helper仅在全部业务检查和自身清理成功后打印最后标记；结合操作员完整回执，限定真实MySQL功能门禁记为通过。

## 通过内容

真实三流service accepted/duplicate、改内容冲突与整批回滚、原payload/稀疏槽位顺序与有限小数/大整数重载、雷达不新增旧raw、不改变患者步态采集时间、stop边界及窗外拒绝。
三项代表性实际数据库拒绝分别取得精确errno1062/1452/3819；不能把这一结果称为全部14外键/13唯一/8CHECK逐项拒绝测试。
cleanup校验本轮标记/归属后只删除自身合成行，并在同事务核对九表全空；没有DROP/TRUNCATE或生产数据删除。

## 未覆盖与下一步

无真实InnoDB竞争/锁等待或规模性能证据，无真实设备/权限/网络/临床或模型效果证据；不声称全量历史测试绿色。
生产lanya尚未执行006，线上B仍为81ddc09，工作台/Agent仍为8647924。后续先只读确认生产前置表和radar表是否存在，再取得生产迁移/服务更新的明确授权。
本回执只记录验收，不自动push、更新ECS或改库；编译通过另为Ru1的构建回报，不等于真机通过。
