# GPS02 uni-app 交付记录

执行日期：2026-10-19 开始，2026-10-20 集中验证与交付。基线 B `2979696`。
权威范围：A `task-GPS02-brief.md`、`2026-10-19-sarcogait-gps-design.md` 第 3–4 节。
本提交只包含 `蓝牙uniapp/` 和本文；不含后端、android-native、加密插件、控制进度文档、生产操作或模型调用。

## 已交付

- `utils/bleTelemetry.js`：按设备连接独立的 LF/CRLF 字节拼行，完整行完成时记录手机 UTC 毫秒；超过 64 KiB 丢到下一 LF；断连/记录窗口切换清半行。严格有限 38 数值及独立 GPS1 13 列；GPS 可选空数值为 null，无 fix/越界坐标仍保留，坏消息计数后继续另一流。
- `utils/collectionSession.js`：明确开始/停止，固定 UUID、clinician/patient/device/start；两流分别递增 sequence，并保存连接 epoch。完整原 GPS 行及 UTC 文本独立；手机时钟回退在最后有效样本时刻停止，不重写时间。UUID 使用运行环境 crypto 或 Android Java UUID，不用随机字符串拼接充当身份。
- `utils/telemetryQueue.js`：持久化后才允许发送；最多 5000 待发事件，到达上限立即停止；另限 100 个未完成采集元数据，防止空会话无限积累。每批同流且最多 50 条，并约束请求编码上限；单飞 FIFO create→events→stop。只在 capture/event/stream 对应且 accepted/duplicate 回执齐全时移除；未知回执保留。
- 网络/超时/5xx 最多自动重试 3 次（初始发送加 3 次重试，共最多 4 次尝试，退避 1/2/4 秒）；4xx/409 不自动重试。达到上限保留数据，用户可重试；相同 UUID、事件内容和停止时间复用，支持响应丢失后的 duplicate 回执。
- 重启只补传持久化窗口，不自动恢复采集；未停止的窗口在最后持久化样本时刻关闭。保存失败停止接收；坏 JSON/结构不能经“重试”覆盖为新空队列，保留原始存储并提示联系维护。持久化失败后的窗口结束信息先保留内存，存储恢复后可人工重试保存。
- `store/modules/blueTooth.js`：真实 UTS 通知回调接入上述模块，未记录时仍显示实时值，移除此入口的每帧旧 raw 上传。每次连接及首连重试独立 epoch；旧连接、延迟服务回调、延迟订阅和旧通知均隔离。意外断连保留会话等待用户重连，清半行且不造缺失样本；主动断开、关蓝牙、删除设备、患者切换、操作员启用/解锁/reset 结束原记录。删除请求发出前先停采，失败也不继续原窗口。
- `api/device.js` 三个新薄封装经原 `api/index.js` 的 export-all 暴露；真实 `request.js` 解开 Response 信封。实际 create/stop 回执仅 `{capture_id}`；batch 为 `{capture_id,results}`。原 raw API 服务/封装仍存在，不新增兼容分支。
- 队列和真实请求拦截器均检查 clinicianId/authEpoch；请求取 JWT 前、401 刷新前后以及重发拦截阶段核验。换操作者不能用新 JWT 发送旧采集；同一原操作者重新解锁后可以人工补传，身份及载荷仍固定。
- 首页沿用现有临床浅色设计（Inter/PingFang、蓝色 `#2F6DF6`、背景 `#F5F7FA`、文字 `#0F172A/#64748B`、原卡片与足图），仅新增设备选择、开始/停止、待传数量/异常说明及 GPS fix/HDOP/sats/age/原速度/接收时间。使用 frontend-design 的一致性和状态文案指导，没有重设计全站、地图 SDK、手机定位权限或质量重评分。GPS 与固件步速分别显示并标来源。
- 采集期间请求屏幕常亮，停止时释放；真实 App `onHide` 停止并保留队列，明确提示保持前台。没有声称操作系统后台/进程被杀时持续可靠采集。

## 环境和 RED 证据

Windows PowerShell；Node `v24.11.0`、npm `11.6.1`、锁定 Vitest `1.6.1`。没有修改 package.json/package-lock.json。

初次 `npm ci --ignore-scripts --no-audit --no-fund` 因全局 npm cache 的 EPERM 失败。
改用可写工作区 cache：

```powershell
cd 'D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1\蓝牙uniapp'
npm ci --ignore-scripts --no-audit --no-fund --cache D:\ME5001\.npm-gps02-cache
```

该安装的终端 session 跨日后不可取，但 npm 自身日志
`D:\ME5001\.npm-gps02-cache\_logs\2026-10-19T14_16_45_173Z-debug-0.log`
末尾 `verbose exit 0`、`info ok`，实际后续测试使用工作树 node_modules。未运行升级命令。

最初解析 RED 保留在本次执行上下文：2026-10-19 22:17:44，真实 `blueTooth.js` 动作在模拟原生通知边界运行，分成两段的 38 列行应刷新实时值，旧代码实际 `hasData=false`。
初次安装尚未完成，因此只读借用主目录已有 Vitest 执行；没有修改脏主目录：

```powershell
node 'D:\ME5001\DataCollectionApp\蓝牙uniapp\node_modules\vitest\vitest.mjs' run tests/collectionWiring.test.js --root 'D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1\蓝牙uniapp' --config 'D:\ME5001\DataCollectionApp\蓝牙uniapp\vitest.config.js' --pool=forks --poolOptions.forks.singleFork
```

结果：`1 failed`，`expected false to be true`，823ms。不是缺失模块/收集错误。

连贯实现后首轮全套 `99 passed`；收尾补测得到以下真实 RED，再修复：

- 2026-10-20 02:08:11：`npm test -- tests/telemetryQueue.test.js --pool=forks --poolOptions.forks.singleFork` → `2 failed,15 passed`。坏 JSON 经人工重试覆盖为空队列，以及坏结构发布状态时抛错；已改为先验证再接管存储，读取失败禁止覆盖。
- 02:10:18：`npm test -- tests/collectionWiring.test.js --pool=forks --poolOptions.forks.singleFork` → `3 failed,9 passed`。首连旧回调造成两次服务扫描、取消通知抛错后 native close 未调用、删除请求开始时 active 尚未停止。修复后同命令 `12 passed`，662ms。
- 02:11:55：queue 同命令 → `1 failed,16 passed`。第 5000 条落缓存后仍未停采；已在接受第 5000 条时立即停止，保留全部 5000 条。

## 集中最终 GREEN

```powershell
cd 'D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1\蓝牙uniapp'
npm test -- --pool=forks --poolOptions.forks.singleFork
git diff --check
git diff --exit-code -- package.json package-lock.json
```

2026-10-20 02:12:06：**15 test files passed，108 passed，0 failed，1.03s**；diff-check 干净，依赖文件无差异。
有既有 Vite CJS Node API deprecation 提示，npm 另打印新版本通知；没有因此升级依赖。

新增 44 个测试：`bleTelemetry` 10、`telemetryQueue` 17、`collectionWiring` 12、`collectionRequest` 5。

关键边界覆盖：每个字节位置拆分/混流/CRLF/64KiB恢复，断连半包，非法有限数/整数、无 fix 空值与越界 GPS；固定患者、操作者/epoch变化、晚到通知、重试旧回调、延迟订阅、意外与主动断连、删除失败、真实患者/操作员动作、真实 App onHide/常亮释放；时钟回退、5000 上限、存储失败与坏持久文档、重启补传、单飞/同流 50 条/FIFO stop、响应丢失复用 ID、错误回执不删、4xx不重试、重试耗尽与人工恢复；真实 device API 路由/DTO 和 request 信封/401 身份门禁；既有运行时隐私日志测试继续通过。

接线测试执行真实 store/API/request/App 动作，仅替换 HBuilderX 提供的 Pinia/原生 BLE/网络/storage 边界；不等同真 Pinia runtime 或 APK 编译。容量测试以 4999 条合成持久事件作为起点，验证第 5000 条及时停止；不冒称已在手机写满真实配额。

## 剩余人工门禁

- 未编译 HBuilderX/APK，未运行 Android/iOS 原生插件、真鞋垫、真实 uni.storage/屏幕常亮/系统 onHide 行为或浏览器视觉验收。原生 Android UUID 和加密插件通知数据类型/回调释放仍须真机验证；未触碰插件源文件。
- 沿用原连接服务列表第 3 项选择，仅增加缺失/无 NOTIFY 的安全拒绝；实际固件服务顺序、原生订阅与异常断连还需实机确认。
- 5000 是应用事件上限，设备存储配额/磁盘故障可能更早停止。未解决系统杀进程前未持久化、系统阻塞通知、同步 storage 写入耗时或无限离线采集问题；未进行吞吐/长时间实机压测。
- 错误/损坏队列保留，未提供自动丢弃、跨操作者转移或绕过 4xx/409 的入口；原操作者须解锁重试，坏存储由维护人员先保全后处理。
- 本地合成动作和拦截器测试不代表实际 B HTTP/RDS/MySQL/ECS/APK 纵向验收；生产迁移与发布由控制任务另行交接。GPS 质量和工作台关联由 B 负责，未将 GPS 送入 Agent/模型。

## GPS02 审查修复第 1 轮（2026-10-20）

唯一 Important：原实现只在重试启动时递增 epoch，首次失败后的 600ms 退避期间及最终失败后，失败 attempt 的 late success 仍会被接纳。先在真实 store 动作补两个窗口的 RED，并补一项失败退休后原 10 秒超时仍执行 native close/取消重试的直接清理检查。

```powershell
cd 'D:\ME5001\.worktrees\DataCollectionApp-snapshot-v1\蓝牙uniapp'
npm test -- tests/collectionWiring.test.js --pool=forks --poolOptions.forks.singleFork
git diff --check
```

02:18:26 RED：`2 failed,13 passed`，683ms；两窗口均实际 `isConnected=true`、应为 false。
修复：初连失败当场递增连接 epoch 并退休该 attempt；operation 的 epoch 同步前移，超时仍能识别当前操作并清理。退避结束使用 operation guard，启动另一新 epoch；旧 attempt 的回调不能使连接复活。最终失败仍清理 timeout/connecting 状态。
02:18:46 GREEN：同一命令 **15 passed，0 failed，688ms**；覆盖两个失败窗口、失败退休后的 timeout/close，以及已有真实接线回归。`git diff --check` 通过，仅 Git 提示测试文件按仓库规则换为 CRLF。

本轮只改 `blueTooth.js`、`collectionWiring.test.js` 和本文；没有重跑 108 项全套，不把定向 15 项与历史全套相加。审查 Minor（非当前采集设备连接成功会清除 waiting）由控制任务保留 deferred，本轮不修改。APK/真机边界不变。
