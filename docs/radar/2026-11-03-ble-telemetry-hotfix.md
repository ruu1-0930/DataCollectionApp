# 鞋垫实时值缺失与待发积压：限定修复及联调记录

日期：2026-11-03。源码提交`3fbc189`；仍在原雷达feature分支。

## 手机实际回执

Ru1回报并提供首页截图：已在共同采集窗口同步记录，原生雷达已连接且有新鲜目标观测，鞋垫/GPS待发为0，雷达待发初始4；随后确认鞋垫/GPS一直为0、压力/加速度实时值缺失、雷达待发持续增加。
不再以未点击开始或旧APK不含原生模块解释本次症状。单次手机原生雷达连接/数据显示已获回执，但不等于三流上传或工作台新会话通过。
待发为0不能区别没有生成事件与事件已确认上传；持续增加也不能单凭计数确定HTTP状态或网络故障根因。

## 可复现的接收回归与修复

1. 旧接收代码`new Uint8Array(data)`支持普通数字数组；新BLE分行器对非ArrayBuffer一律读取`.buffer/byteOffset/byteLength`。普通数字数组没有这些属性，会被转换为长度0，既不更新实时值，也不产生上传事件，且不增加格式错误计数。
2. 新38字段解析引入`Object.fromEntries`；缺该API时抛错而被记作坏协议。保持原字段/顺序/严格数字校验，以字段遍历构造相同payload，恢复旧接收代码不依赖该API的能力，不增加全局polyfill。

修复仅改`蓝牙uniapp/utils/bleTelemetry.js`：ArrayBuffer或普通数组沿原Uint8Array构造，typed view继续保留offset/length；38字段通过forEach赋值。GPS、换行边界、溢出丢弃、事件/队列/ID/后端协议不变。
尚无手机真实通知类型或引擎API清单，因此这是源级确定性回归修复，不声称已证明截图唯一根因；不修改加密BLE插件，不猜未带换行消息的边界。

## 实际验证

新增回归先3failed/25passed，分别覆盖数字数组分行、缺Object.fromEntries的38解析、真实store通知动作的压力/IMU及上传。

```powershell
.\node_modules\.bin\vitest.cmd run tests/bleTelemetry.test.js tests/collectionWiring.test.js tests/collectionRuntime.test.js tests/collectionCoordinator.test.js tests/radarWiring.test.js --pool=forks --poolOptions.forks.singleFork
```

修复后5文件51passed/853ms，Vite CJS既有warning保留。真实store测试检查压力/六轴值、38字段及insole batch派发；原严格数字、分片重组及三流队列回归保持。
独立限域只读审查3fbc189三个文件：0Critical/0Important、无阻止交付的Minor，可交付源码复测；审查者没有重跑51项或验手机。

## 上传仍需定位

已核对真实请求拦截器返回`response.data.data`，与coordinator所需receipt相符；不能把已有正确解包当作本次修复对象。
雷达native HTTP仅对雷达连接/UDP绑定所选Wi-Fi Network，没有发现全进程网络绑定；没有证据据此断言它把云端请求强制绑到无外网Wi-Fi。
工作台gait会话来自鞋垫DeviceRawData；radar侧流不写这些行，单有雷达记录不会新建步态会话。手机与网页还须选中同一患者，不在记录中保存患者/设备标识。

下一步Ru1停止本轮记录并保留待发后，保持雷达Wi-Fi，在同一手机浏览器只读访问`https://api.sarcopenianus.com/account/context`；无登录返回Token缺失可验证该浏览器公网可达，但不证明App上传或鉴权成功。
打不开则先定位该手机到公网的链路；能打开则继续取得采集POST的状态码或队列暂停原因，再判断网络、401/403、4xx协议或5xx。未取得这些证据前不改RDS、放宽校验或绕过鉴权。
后续实际回执：Ru1在同一手机、保持雷达Wi-Fi下打开上述地址，回复Token缺失；该浏览器到公网API可达门禁通过，不能继续按Wi-Fi无外网处理。它不证明uni.request采用相同网络/证书路径或携带有效Token。下一步人工只读ECS Nginx最近采集POST日志，输出时间、create/batch/stop分类及HTTP码，隐藏IP、患者/设备/capture及Token；无匹配只表示限定日志窗口未检出，不推断全局从未请求。
本地一次公网curl在DNS阶段超时，浏览器读取工具遇kernel assets/os error3，均是控制者侧未完成检查，不作为ECS服务故障证据，不反复重试或清理用户环境。

## Ru1复测及未验

使用同一`D:/ME5001/.worktrees/DataCollectionApp-indoor-radar/蓝牙uniapp`源码完整APK同签名覆盖安装，保留患者/持久队列；手机物理安装与测试由Ru1执行。
连接鞋垫后即应有实时预览，展开IMU卡查看六轴；显式开始记录后分别观察两lane待发及上传结果，再在工作台选择相同患者/采集时段刷新。
目前雷达原生接收已回报通过，修复APK的鞋垫显示/采集及云端上传尚未回报，含新帧的工作台会话仍待验。没有push、后端变更、ECS/RDS操作或模型调用；双语工作独立保留。
先取得采集HTTP状态码，再将已修复的BLE接收与有证据支持的上传修复一并交付，避免让Ru1每个猜测重打一次APK；当前不追加无证据的上传逻辑更改。

## 后续服务器HTTP回执

Ru1提供11月3日北京时间14:50:29–14:50:38连续batch HTTP200及stop HTTP200，随后14:51:03 create HTTP200、14:51:20 stop HTTP200。当前片段没有4xx/5xx，确认限定请求已到达B并返回成功；不继续把待发增长本身当作上传故障证据。
源码中CollectionError/鉴权/数据库异常返回相应非200；batch成功可以包含accepted或幂等duplicate。App仅在两lane待发均空且记录已停止后发送stop，但日志已隐藏capture标识，无法逐一关联截图中的记录，不能称所有队列均清空或全部三流已落库。
下一步只读核对手机所选患者当天最近采集的insole/GPS/radar分表计数及采集起止时间，不输出payload或位置。若仅radar有记录且insole为0，则旧工作台无新gait会话与依赖鞋垫raw的设计一致；恢复38接收仍需3fbc189修复APK复测。
当前不增加上传代码或后端变更；HTTP200只关闭这段成功响应证据，分表落库/新帧工作台与真机补丁效果继续待验。
