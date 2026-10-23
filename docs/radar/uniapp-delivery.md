# 室内雷达uni-app交付记录

2026-10-24模块审查续修：原生probe超时不再冒充整轮取消，可读v2恢复freeze-stop写失败可手动先持久化再发送。
独立复审两项ADDRESSED，quality approved。必要四文件45passed/1.31s（此前完整受影响块82passed），
不将两次结果相加；Vite告警仍在，UTS/APK/权限/真机门禁不关闭。实际提交与统一进度见Project雷达进度表。

R02a本地JS验证：24 passed/4 files/1.05s；Vite CJS deprecation。独立UTS+Kotlin原生适配、严格协议、有界自动发现与单飞轮询已实现；原38/GPS解析回归通过。未连接真实LAN。

原生门禁仍开放：本机未找到HBuilderX/ADB/kotlinc，UTS/Kotlin未编译、最终合并manifest未核对、APK/真机未验。mock通过不证明可打包。HBuilderX>=4.25，保持原minSdk；API<23/非Android unsupported，原38/GPS保留。

项目未固定targetSdk，须检查实际APK。当前不启用Android16 LAN opt-in；如构建开启，须核对NEARBY_WIFI_DEVICES权限路径。target>=37且设备API>=37需声明并运行时申请ACCESS_LOCAL_NETWORK；当前不盲加该新权限，若缺声明明确permission停止雷达。原生仅一次按需弹窗，拒绝后提示去系统设置，不能用手填IP绕过。

动态私网IP需要usesCleartextTraffic原生配置，不能表达CIDR白名单；专用原生客户端及JS限制RFC1918:80/api/targets，无云凭据/重定向/任意URL。云端HTTPS/sslVerify保持。最终APK需验证设备HTTP、云HTTPS、Wi-Fi Network绑定、取消与组播锁释放。

依赖按现有package-lock npm ci，122 packages；npm报告8 vulnerabilities（2 moderate/4 high/2 critical），未改锁/升级。

## R02b（2026-10-24，本地实现待审）

唯一collectionCoordinator接create/stop/身份/持久回执，telemetryQueue改为纯单lane工具；version2含primary(insole+gps)与radar两个独立5000容量outbox，100个capture上限。旧key显式v1→v2迁移保原ID/created/stop，迁移写失败保旧字节并停发。恢复关闭时间覆盖三流最新持久样本，所有回执完成才stop，同ID重传。

正式BLE通知与独立HTTP轮询接同一capture；HTTP开始冻结患者/操作者/authEpoch/capture/生命周期token。RadarPanel已挂首页，App后台停止三流，前台只恢复连接；患者切换/退出/主动断连都使旧回调失效。雷达容量/上传暂停不阻断原流，瞬时重试退避期间新鞋垫可立即唤醒调度；存储介质失败仍可能影响各流。

最终限定验证：82 passed/9 files/1.65s/exit0，Vite CJS告警保留。命令（B/蓝牙uniapp，PATH含C:/Program Files/nodejs，TEMP/TMP为D:/ME5001/runtime/workbench-remediation-temp）：

```powershell
& '.\node_modules\.bin\vitest.cmd' run tests/collectionCoordinator.test.js tests/radarWiring.test.js tests/telemetryQueue.test.js tests/collectionWiring.test.js tests/collectionRequest.test.js tests/radarProtocol.test.js tests/radarDiscovery.test.js tests/radarLink.test.js tests/bleTelemetry.test.js
```

覆盖双outbox stop、雷达失败/容量隔离、恢复覆盖最后雷达、迁移保ID/失败保原字节、请求凭据围栏、真实BLE与HTTP正式store接线、后台/退出/跨患者晚回调、权限拒绝后旧采集、协议错误网络失败计数、取消仍限5Hz。RED过程及精确28个文件见A树task-R02b-report.md。git diff --check exit0（另LF→CRLF提示）。未stage/commit/push。

这些测试不证明UTS/Kotlin/UI可编译、最终manifest权限正确、APK/真实Wi-Fi/硬件已验收。Android16 opt-in配置/授权路径仍缺验证和配套配置；target>=37的新权限声明及最终target仍须打包核对。原生/权限/MySQL/RDS/ECS门禁独立保留。

v2队列旧APK不能读；上线/降级前导出或发完待发并人工确认，不承诺降级兼容。本轮未提供通用迁移/导出工具，待发不自动清除。
