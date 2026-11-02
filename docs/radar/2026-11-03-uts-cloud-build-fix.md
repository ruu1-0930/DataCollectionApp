# 雷达 UTS 云打包参数命名修复

日期：2026-11-03。源码提交：`cdf4831`，分支`feature/sarcogait-indoor-radar-v1`。

## 实际日志与定位

Ru1提供的日志包含一次Gradle项目解析失败`Project with path ':uni_modules:sarcogait-radar' could not be found`，及随后两次`:uni_modules:sarcogait-radar:compileReleaseKotlin`失败。
后两次明确定位云端生成的`utssdk/app-android/src/index.kt:66:39`，错误为全下划线名称保留，最终UTS插件错误码-5000；弃用API提示本身不是这次编译错误。

本地项目为普通uni-app/Vue3加UTS插件，manifest中的AppID与日志`__UNI__6AC6D10`一致。插件package ID、根目录导入及app-android入口存在；后两次任务名说明这些构建已经识别到雷达子模块。
首次模块缺失的具体原因不能仅凭合并日志确认，不将它直接解释为缺Gradle依赖或本次命名问题的必然结果。

源码`蓝牙uniapp/uni_modules/sarcogait-radar/utssdk/app-android/index.uts`第21行的权限回调使用`_: string[]`和`(_: boolean, __: string[])`。
将回调参数改为具名`allRight/grantedList`及`doNotAskAgain/grantedList`；仅更名/换行，成功仍resolve(allRight)，失败仍resolve(false)，权限请求和返回结构不变。
这是针对当前UTS生成代码错误的最小源修正。没有云端生成index.kt原文，不能声称已逐字比对生成行；须以重新云打包结果关闭原生编译门禁。

参数签名依据[DCloud UTSAndroid文档](https://doc.dcloud.net.cn/uni-app-x/uts/utsandroid.html#requestsystempermission)。UTS目录/Android混编文件和云端打包配置见[DCloud插件规范](https://uniapp.dcloud.net.cn/plugin/uts-plugin.html)。
Kotlin对单下划线在lambda、catch等特定位置有合法用法，不能将报错外推为所有下划线都禁止；本次未修改RadarNative.kt中的catch，也未改云端生成Gradle/原生配置。

## 实际验证

新增`tests/radarUtsPermission.test.js`的回归：UTS回调参数不含全下划线标识符；执行去除类型注解后的原capabilities函数体，检查成功/拒绝/已授权路径保留原行为。
先运行新文件，实际1failed/3passed，失败检测到`['_', '_', '__']`；随后更名并运行：

```powershell
.\node_modules\.bin\vitest.cmd run tests/radarUtsPermission.test.js tests/radarAppPlatform.test.js tests/radarNativeScope.test.js tests/radarWiring.test.js --pool=forks --poolOptions.forks.singleFork
```

结果4文件15passed/777ms，保留既有Vite CJS warning。源码命名检查及JS执行seam不代替UTS转译/Kotlin编译、HBuilderX云打包、最终manifest/权限或真机连接；控制者未操作HBuilderX。

## Ru1重新打包

1. HBuilderX打开`D:/ME5001/.worktrees/DataCollectionApp-indoor-radar/蓝牙uniapp`，确认修复后的index.uts已保存；插件声明HBuilderX>=4.25。
2. 重新提交完整Android APK云打包，使原生UTS插件重新编译；不使用仅WGT/JS更新替代原生构建。不手改云端生成的index.kt或app/build.gradle。
3. 若仍出现模块缺失，先确认当前提交包含整个`uni_modules/sarcogait-radar`（package.json、utssdk/interface.uts、app-android的index.uts、RadarNative.kt、config.json、AndroidManifest.xml），根目录JS导入正确。本地结构目前完整，不凭此错误盲目添加`implementation project(...)`或移入nativeplugins。
4. 如仍报同一保留名称，核对这次打包所选项目路径和保存后的参数，再提供最后一次完整错误及HBuilderX版本；不要将不同构建的多段日志当成同一次失败。
5. 云打包成功后沿用原签名完整APK覆盖升级，保留患者与待发缓存，继续设备复测；不卸载/清手机缓存。本补丁不涉及B、RDS、工作台或Agent，ECS无需更新。

当前仅本地提交，尚未push；实际APK编译/安装/手机雷达仍待Ru1反馈，双语任务保持进行中。
