# 手机采集缓存提示与雷达加载修复

源码提交：`038fe20`，分支`feature/sarcogait-indoor-radar-v1`。
日期：2026-11-02。Ru1真机反馈连接鞋垫后不久出现“缓存不可用，已停止记录”，截图同时显示雷达不支持。

## 可复现问题及修复

1. 新协调器在入队、停止和恢复时使用`Array.at`，恢复还使用`Array.flatMap`。缺少这些方法时，即使存储API正常，第一帧处理也会异常并被归为storage；已有打开的采集窗口恢复也会误判不可读。改为基础reduce和循环取同一有效UTC时间最大值，不添加全局polyfill，不改变任何事件、capture ID、持久队列格式、确认删除或真实存储失败保护。
2. `utils/radarNative.js`在普通uni-app JS中使用`APP-ANDROID`，导致默认插件分支被条件编译删除。改用`APP-PLUS`并在运行时限定Android；注入式测试路径保留，web/iOS默认不调用Android插件。

条件编译依据：[DCloud官方平台文档](https://uniapp.dcloud.net.cn/tutorial/platform.html)。普通uni-app项目的`APP-ANDROID`只在UTS文件支持；JS的App平台用`APP-PLUS`。

这是源码级复现和修复，没有手机引擎日志，不能仅凭截图断言该手机的所有缓存失败均已找到原因。

## 实际验证

新增两文件回归先RED：7failed/2passed，失败准确覆盖三流接收、v1/v2打开窗口恢复、stop及普通Android JS默认插件。

```powershell
.\node_modules\.bin\vitest.cmd run tests/collectionRuntime.test.js tests/radarAppPlatform.test.js tests/collectionCoordinator.test.js tests/collectionWiring.test.js tests/radarNativeScope.test.js tests/radarWiring.test.js --pool=forks --poolOptions.forks.singleFork
```

修复后六文件43passed/15.38s，Vite CJS既有warning保留。真实存储失败/迁移失败保原字节等保护由既有协调器回归继续覆盖；没有重复后端/MySQL/历史矩阵。
独立限域审查0Critical/0Important，源码可交付复测；Minor覆盖机会为缺API时radar最后时间及乱序样本的直接组合回归，源码取max和遍历双lane已核对，暂缓追加矩阵。
平台测试为手工条件预处理+注入，不等同HBuilderX、UTS模块解析、iOS编译或真机雷达运行通过。

## Ru1重新打包及手机复测

源目录：`D:/ME5001/.worktrees/DataCollectionApp-indoor-radar/蓝牙uniapp`。由Ru1自行使用HBuilderX构建完整Android APK，确保原生雷达模块被实际打入包；不操作HBuilderX，不改签名、manifest或依赖锁。
沿用原App身份/签名覆盖升级并保留本地数据；不要卸载、清缓存或删除collection_queue_v1来绕过报错。

复测：启动并连接鞋垫，先观察实时值；显式开始同步记录后接收38字段/GPS，保持一小段记录再停止，查看待发队列能否下降及服务器是否有新会话；重启确认旧待发仍保留。雷达模块应进入能力/权限/Wi-Fi判断，而不是因JS导入被裁剪一律显示不支持。
若仍失败，回报发生在启动/开始/第一帧/停止哪一步及手机系统/App构建版本；不发送账号口令、患者定位或缓存原文。

本次仅App两源码文件，无B服务/数据库/Agent变更，ECS无需为此补丁再次迁移或重启。源码已本地提交，尚未push；新APK构建、安装与设备复测均待Ru1反馈。

## 2026-11-03 手动配置弹窗及设备版本确认

Ru1明确回复“还没重新打包”。因此目前手机提示“此系统暂不支持雷达”来自修复前安装包，尚未验证038fe20的模块加载修正；手动填写IP也必须通过原生能力/权限判断，不能使缺失模块变为支持。

本次按要求将首页常驻IP输入移入既有uni-popup居中弹窗：点“手动配置”填写地址，取消关闭且保留本次输入；空地址、非私网或非法IPv4留在弹窗提示，不改变现有连接；合法地址去除两端空格后关闭弹窗，交给原radar.connect。连接结果仍在卡片显示，不改变自动发现、轮询或采集逻辑。

新增测试先5failed（旧页面无弹窗处理器），实现后运行：

```powershell
.\node_modules\.bin\vitest.cmd run tests/radarManualConfig.test.js tests/radarAppPlatform.test.js tests/radarLink.test.js tests/radarWiring.test.js --pool=forks --poolOptions.forks.singleFork
```

结果四文件25passed/788ms，Vite CJS既有warning保留。新测试执行组件真实setup处理器，覆盖打开/取消、三类非法输入和合法地址单次派发；既有测试覆盖默认Android插件加载及连接/采集接线。本地没有Vue/原生渲染器，未执行HBuilderX模板编译、键盘遮挡或设备雷达测试。

重新打包仍使用本文同一源目录；完整APK同签名覆盖安装以保留待发数据。先检查手动配置是否弹窗，再连接鞋垫观察缓存提示与显式记录；手机连雷达同一Wi-Fi后检查自动发现/手动连接。如修复包仍unsupported，再记录手机系统版本与构建输出中原生模块是否实际包含，不重复试不同IP来绕过检查。此次无需ECS更新。
