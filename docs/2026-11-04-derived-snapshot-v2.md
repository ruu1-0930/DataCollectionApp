# 派生质量快照V2：后端接线

本块承接D01，新增显式启用的SnapshotPipeline(schema_version='2')；默认仍构建V1。配套SnapshotVersions的snapshot_schema_version/projection_schema_version均为2，analyzer_set_version为snapshot-pipeline-v3。A消费者尚未实现V2，不单独部署/开启该新写路径。

V2使用独立gait_snapshot_v2.schema.json，旧gait_snapshot_v1.schema.json字节不改。V2完整快照和Agent投影都要求derivation_quality@1，provenance明确新版本。诊断使用同次冻结源加载和过滤后构建的frames；不额外查库、不从前500个图表点推断，不改原指标数值、阈值或门禁。

诊断与新增quality.derivation证据指针参与完整快照/投影hash，并在发布时检查两份共享内容完全相等。诊断计算失败停止V2构建，不生成空诊断伪装成功；类型/未知字段/布尔计数/数量不守恒均拒绝。available继续仅描述公式输入群体，不保证最终CV存在或临床可信。

读取按已存快照行版本选对应严格契约与投影，而不是按当前部署的写版本猜测旧记录。SQLite合成发布验收：先建V1再建V2，两个ID不同；新V2可幂等复用；V2服务仍能读旧V1完整快照及投影；旧canonical_payload逐字不变。未执行RDS/MySQL迁移，新数据仍存既有JSON payload列。

## 实际验证与限制

首次旧venv缺jsonschema造成collection error，未计产品RED；改用既有D:/ME5001/runtime/gps-backend-dev/.venv，无依赖安装后新文件8failed（V2构造、阶段、版本未支持）。实现后7failed/1passed，为V2证据指针仍引用V1允许路径；改成独立EvidencePointerV2后8passed/10既有warnings。

最终五文件：test_snapshot_derivation_v2、test_gait_derivation_quality、test_snapshot_pipeline、test_analysis_snapshot_service、test_snapshot_repository，113passed/232既有warnings/12.77s。告警为sklearn probability弃用及SQLAlchemy utcnow，不记成已修。命令在B根目录，PYTHONPATH=back、TEMP/TMP=Git外可写目录：

```text
python -m pytest -p no:cacheprovider back/tests/test_snapshot_derivation_v2.py back/tests/test_gait_derivation_quality.py back/tests/test_snapshot_pipeline.py back/tests/test_analysis_snapshot_service.py back/tests/test_snapshot_repository.py -q --tb=line --basetemp D:/ME5001/runtime/workbench-remediation-temp/derived-v2-reproduce-new
```

使用上述runtime虚拟环境；每次换新basetemp。通过证明限定本地SnapshotPipeline/SQLite发布读取路径，不代表A消费者、模型效果、真实采集、ECS Python3.10或MySQL验收。没有模型/网络/浏览器/设备/生产操作，用户uni-app manifest改动未动。正式A双语页面与Agent接线仍是D02消费者及D03/D04待办，本块不标全链路已完成。

审查首轮0C/1Important/1Minor：Important为左右样本交集缺守恒下界，可接受L=R=total但paired=0及无单侧样本却成功比较。新增3项真实RED后修复交集下界/incomplete与paired互补/成功比较双侧非空；保留合法左右错开窗口。Minor为错误V2 analyzer延后失败，新增RED后前置构造拒绝（显式注入producer能力保留）。最后新文件13passed/14既有warnings/3.92s；与前113项重叠不相加。同审查者限域复核两项ADDRESSED，剩余0C/0I/0M，合法错开窗口与注入producer能力保留。复核仅纯内存探针，不加总为模型或全链效果指标。
