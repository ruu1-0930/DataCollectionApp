# 步态采集 App 原生化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 uni-app 采集端 App 1:1 重写为 Android 原生（Kotlin + Jetpack Compose）App，保留临床流程、后端契约与蓝牙采集行为不变。

**Architecture:** 单 Activity + Compose Navigation；MVVM（ViewModel + StateFlow 对应 Pinia store）；Repository 编排网络/蓝牙/本地存储；蓝牙复用仓库内开源 fastble Java 源码；纯逻辑独立成可单测的 Kotlin 函数。

**Tech Stack:** Kotlin、Jetpack Compose、Navigation-Compose、Retrofit + OkHttp + kotlinx-serialization、DataStore(Preferences)、Lifecycle-ViewModel-Compose、vendored `com.clj.fastble`、JUnit4。

**关键参照源（旧工程，逐文件对照，勿改）：** `蓝牙uniapp/`
- 蓝牙编排：`store/modules/blueTooth.js`
- 网络/401：`utils/request.js`、`config/index.js`
- 业务 store：`store/modules/{operator,patient}.js`、`utils/clinicStorage.js`、`utils/auth.js`、`utils/terminal.js`
- 纯逻辑：`utils/{footMetrics,apiShape,patient}.js`
- 屏幕：`pages/**`、组件 `components/base/Ca*.vue`、令牌 `styles/tokens.scss`

**环境既定事实：** Android Studio 在 `D:\Program Files (x86)\Android Studio`（JBR=OpenJDK 21）；SDK 在 `C:\Users\Lenovo\AppData\Local\Android\Sdk`（platform android-36、build-tools 36/37、platform-tools）。新工程目录 = `DataCollectionApp/android-native/`。

---

## File Structure

```
android-native/
  settings.gradle.kts            # 单 app 模块
  build.gradle.kts               # 顶层插件版本
  gradle.properties              # JDK 固定 + AndroidX 开关
  local.properties               # sdk.dir（gitignore）
  gradlew / gradlew.bat / gradle/wrapper/*
  .gitignore
  app/
    build.gradle.kts
    src/main/AndroidManifest.xml
    src/main/java/com/clj/fastble/**            # vendored 第三方（原样）
    src/main/java/com/sarcopenianus/collector/
      MainActivity.kt
      core/
        InsoleFrame.kt            # 38 字段数据类
        InsoleFrameParser.kt      # CSV→帧（纯逻辑）
        FootMetrics.kt            # shade / mToCm（纯逻辑）
        TerminalCode.kt           # 终端码生成（纯逻辑）
        PatientLogic.kt           # 校验/脱敏/搜索（纯逻辑）
      data/
        net/
          ApiModels.kt            # DTO + 信封
          ApiService.kt           # Retrofit 接口
          ApiShape.kt             # DTO↔UI 形状映射（纯逻辑）
          Network.kt              # Retrofit/OkHttp 装配
          AuthInterceptor.kt      # Bearer 注入 + 401 静默重试
        local/
          LocalStore.kt           # DataStore 封装
      domain/
        OperatorRepository.kt
        PatientRepository.kt
        BleRepository.kt          # fastble 编排 + realtime
        RealtimeModels.kt         # Realtime/FootRealtime 状态
      ui/
        theme/{Color.kt,Type.kt,Theme.kt}
        components/{CaCard,CaInput,CaEmpty,CaMetric,CaStatusStrip,CaPatientBar}.kt
        nav/AppNav.kt             # 路由 + 启动网关 + 底部 Tab
        screens/{Enable,Unlock,PatientSelect,PatientNew,Home,Data,Mine}Screen.kt
        vm/{OperatorViewModel,PatientViewModel,BleViewModel}.kt
    src/main/res/
      drawable/foot.png           # 从旧工程 static/imgs/foot.png 复制
      values/{strings.xml,themes.xml}
      mipmap-*/                   # 应用图标（从旧 unpackage/res/icons 转）
    src/test/java/com/sarcopenianus/collector/   # JUnit 纯逻辑单测
```

---

## Phase 0 — 工程骨架与环境（隔离，复用已装 SDK/JBR）

### Task 0.1: 创建 Gradle 骨架与环境固定

**Files:**
- Create: `android-native/settings.gradle.kts`
- Create: `android-native/build.gradle.kts`
- Create: `android-native/gradle.properties`
- Create: `android-native/local.properties`
- Create: `android-native/.gitignore`
- Create: `android-native/gradle/wrapper/gradle-wrapper.properties`

- [ ] **Step 1: settings.gradle.kts**

```kotlin
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "GaitCollector"
include(":app")
```

- [ ] **Step 2: 顶层 build.gradle.kts（锁版本，兼容 JDK21 + compileSdk36）**

```kotlin
plugins {
    id("com.android.application") version "8.11.1" apply false
    id("org.jetbrains.kotlin.android") version "2.1.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.21" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.1.21" apply false
}
```

> 若 Android Studio 同步报版本不兼容，按其建议把 AGP/Kotlin/Gradle 升到最近的稳定一致组合后，更新本任务记录的版本号。

- [ ] **Step 3: gradle.properties（固定 JBR，不动系统 PATH）**

```properties
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.useAndroidX=true
kotlin.code.style=official
android.nonTransitiveRClass=true
org.gradle.java.home=D:\\Program Files (x86)\\Android Studio\\jbr
```

- [ ] **Step 4: local.properties（机器本地，引用已装 SDK）**

```properties
sdk.dir=C\:\\Users\\Lenovo\\AppData\\Local\\Android\\Sdk
```

- [ ] **Step 5: gradle-wrapper.properties（项目内 Gradle，不依赖系统）**

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

- [ ] **Step 6: .gitignore**

```gitignore
local.properties
.gradle/
build/
.idea/
*.iml
.kotlin/
captures/
```

- [ ] **Step 7: 生成 wrapper 脚本并验证 JDK**

用 Android Studio 打开 `android-native/` 触发 Gradle sync（会补全 `gradlew`/`gradlew.bat`/`gradle-wrapper.jar`）。或在已装 Studio 的终端用其 Gradle 生成 wrapper。
Run（项目根，PowerShell）：`.\gradlew.bat --version`
Expected：`JVM: 21.0.x`（来自 JBR），`Gradle 8.14`。

- [ ] **Step 8: Commit**（与 spec 一同提交，见执行结束时）

### Task 0.2: app 模块 + 空 Compose Activity，真机跑通

**Files:**
- Create: `android-native/app/build.gradle.kts`
- Create: `android-native/app/src/main/AndroidManifest.xml`
- Create: `android-native/app/src/main/java/com/sarcopenianus/collector/MainActivity.kt`
- Create: `android-native/app/src/main/res/values/strings.xml`
- Create: `android-native/app/src/main/res/values/themes.xml`

- [ ] **Step 1: app/build.gradle.kts**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}
android {
    namespace = "com.sarcopenianus.collector"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.sarcopenianus.collector"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.navigation:navigation-compose:2.8.5")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("com.jakewharton.retrofit:retrofit2-kotlinx-serialization-converter:1.0.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}
```

- [ ] **Step 2: AndroidManifest.xml（含蓝牙全量权限，对照旧 manifest.json）**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.BLUETOOTH" android:maxSdkVersion="30" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADMIN" android:maxSdkVersion="30" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" android:maxSdkVersion="30" />
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
    <uses-feature android:name="android.hardware.bluetooth_le" android:required="true" />
    <application
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.GaitCollector">
        <activity android:name=".MainActivity" android:exported="true"
            android:theme="@style/Theme.GaitCollector">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

> 注：`BLUETOOTH_SCAN` 暂不加 `neverForLocation`，因旧逻辑在 Android 11- 用定位扫描，保留位置语义以对齐现状。

- [ ] **Step 3: strings.xml / themes.xml**

```xml
<!-- values/strings.xml -->
<resources><string name="app_name">步态采集</string></resources>
```
```xml
<!-- values/themes.xml -->
<resources>
    <style name="Theme.GaitCollector" parent="android:Theme.Material.Light.NoActionBar" />
</resources>
```

- [ ] **Step 4: 临时图标**

把旧工程 `蓝牙uniapp/unpackage/res/icons/192x192.png` 复制为 `app/src/main/res/mipmap-xxxhdpi/ic_launcher.png`（其余密度可暂复用同图）。

- [ ] **Step 5: MainActivity.kt（空壳，验证可跑）**

```kotlin
package com.sarcopenianus.collector

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { App() }
    }
}

@Composable
fun App() { Text("步态采集 — 脚手架就绪") }
```

- [ ] **Step 6: 构建并真机安装**

Run：`.\gradlew.bat :app:assembleDebug`
Expected：`BUILD SUCCESSFUL`，产出 `app/build/outputs/apk/debug/app-debug.apk`。
真机（开发者模式+USB 调试）：`& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r app\build\outputs\apk\debug\app-debug.apk`，打开见「脚手架就绪」。

- [ ] **Step 7: Commit**

---

## Phase 1 — Vendored 蓝牙引擎

### Task 1.1: 复制 fastble Java 源码并编译通过

**Files:**
- Create: `android-native/app/src/main/java/com/clj/fastble/**`（整树）
- Copy: `android-native/app/src/main/java/com/clj/fastble/`（来自 `蓝牙uniapp/uni_modules/android-ble/utssdk/app-android/com/clj/fastble/`）
- Copy: `ByteUtil.java`、`Result.java`（同源目录）到对应包

- [ ] **Step 1: 原样复制源码**

把旧工程 `蓝牙uniapp/uni_modules/android-ble/utssdk/app-android/com/clj/fastble/**` 全部文件复制到 `app/src/main/java/com/clj/fastble/`（保持包结构）。同时复制 `ByteUtil.java`、`HexUtil.java`（已在 utils/ 内）。**不要复制** `index.uts`、`BleHelper.kt`、`config.json`、`AndroidManifest.xml`（这些是加密壳/插件元数据）。

- [ ] **Step 2: 修正编译依赖**

fastble 仅依赖 Android SDK（`android.bluetooth.*`）。若有 `import` 指向 uts/插件运行时（如 `io.dcloud`/`uts`），定位后删除相关无用类或方法（这些是 UTS 桥用，不会被原生调用）。逐个编译错误处理。

- [ ] **Step 3: 编译验证**

Run：`.\gradlew.bat :app:compileDebugKotlin :app:compileDebugJavaWithJavac`
Expected：`BUILD SUCCESSFUL`（fastble 全部编译通过，无 uts 依赖残留）。

- [ ] **Step 4: Commit**

---

## Phase 2 — 纯逻辑（TDD，JUnit）

> 全部以旧工程 `utils/*.js` + 其 vitest 用例为对照基准。每个任务：先写失败测试 → 跑红 → 实现 → 跑绿 → 提交。

### Task 2.1: FootMetrics（热力着色 / 单位换算）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/core/FootMetrics.kt`
- Test: `app/src/test/java/com/sarcopenianus/collector/core/FootMetricsTest.kt`

对照 `utils/footMetrics.js`：PMAX=4093；LOW=(219,234,254) `#dbeafe` → HIGH=(29,78,216) `#1d4ed8` 线性插值；非数值/缺失按 0；超量程钳到 1；`mToCm` 非数值/null 返回 NaN，否则 ×100。原生用 `Int` ARGB 颜色（`0xFF` alpha）。

- [ ] **Step 1: 写失败测试**

```kotlin
package com.sarcopenianus.collector.core
import org.junit.Assert.*
import org.junit.Test

class FootMetricsTest {
    @Test fun shade_zero_isLow() {
        assertEquals(0xFFDBEAFE.toInt(), FootMetrics.shade(0.0))
    }
    @Test fun shade_max_isHigh() {
        assertEquals(0xFF1D4ED8.toInt(), FootMetrics.shade(4093.0))
    }
    @Test fun shade_overMax_clampsToHigh() {
        assertEquals(0xFF1D4ED8.toInt(), FootMetrics.shade(9999.0))
    }
    @Test fun shade_nan_isLow() {
        assertEquals(0xFFDBEAFE.toInt(), FootMetrics.shade(Double.NaN))
    }
    @Test fun shade_mid_interpolates() {
        // t=0.5 → round(219+(29-219)*.5)=124, round(234+(78-234)*.5)=156, round(254+(216-254)*.5)=235
        assertEquals(0xFF7C9CEB.toInt(), FootMetrics.shade(4093.0 / 2))
    }
    @Test fun mToCm_value() { assertEquals(123.0, FootMetrics.mToCm(1.23), 1e-9) }
    @Test fun mToCm_null_isNaN() { assertTrue(FootMetrics.mToCm(null).isNaN()) }
}
```

- [ ] **Step 2: 跑红** — `.\gradlew.bat :app:testDebugUnitTest --tests "*FootMetricsTest"` → 编译失败（类未定义）。

- [ ] **Step 3: 实现**

```kotlin
package com.sarcopenianus.collector.core

object FootMetrics {
    const val PMAX = 4093.0
    private val LOW = intArrayOf(219, 234, 254)
    private val HIGH = intArrayOf(29, 78, 216)

    fun shade(adc: Double?): Int {
        val v = adc ?: Double.NaN
        val t = if (v.isFinite()) (v / PMAX).coerceIn(0.0, 1.0) else 0.0
        val r = Math.round(LOW[0] + (HIGH[0] - LOW[0]) * t).toInt()
        val g = Math.round(LOW[1] + (HIGH[1] - LOW[1]) * t).toInt()
        val b = Math.round(LOW[2] + (HIGH[2] - LOW[2]) * t).toInt()
        return (0xFF shl 24) or (r shl 16) or (g shl 8) or b
    }

    fun mToCm(m: Double?): Double {
        if (m == null) return Double.NaN
        return if (m.isFinite()) m * 100 else Double.NaN
    }
}
```

- [ ] **Step 4: 跑绿** — 同命令 → PASS。
- [ ] **Step 5: Commit**

### Task 2.2: InsoleFrame + InsoleFrameParser（38 字段解析）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/core/InsoleFrame.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/core/InsoleFrameParser.kt`
- Test: `app/src/test/java/com/sarcopenianus/collector/core/InsoleFrameParserTest.kt`

对照 `blueTooth.js:283-355`：字符串按 `,` split、去 `\n`，长度必须 = 38，否则返回 null；字段顺序固定（左 0–18，右 19–37）。`InsoleFrame` 字段名对齐后端上传命名（`lp1..lp9, ax..gz, left_step_size, left_speed, left_single_sp_time, left_double_sp_time, rp1..rp9, right_ax..right_gz, right_step_size, right_speed, right_single_sp_time, right_double_sp_time`）。

- [ ] **Step 1: 写失败测试**

```kotlin
package com.sarcopenianus.collector.core
import org.junit.Assert.*
import org.junit.Test

class InsoleFrameParserTest {
    private fun line(n: Int) = (0 until n).joinToString(",") { it.toString() }

    @Test fun wrongLength_returnsNull() {
        assertNull(InsoleFrameParser.parse(line(37)))
        assertNull(InsoleFrameParser.parse(line(39)))
    }
    @Test fun parses38_mapsOrder() {
        val f = InsoleFrameParser.parse(line(38))!!
        assertEquals(0.0, f.lp1, 0.0)        // idx 0
        assertEquals(8.0, f.lp9, 0.0)        // idx 8
        assertEquals(9.0, f.ax, 0.0)         // idx 9
        assertEquals(15.0, f.leftStepSize, 0.0) // idx 15
        assertEquals(19.0, f.rp1, 0.0)       // idx 19
        assertEquals(37.0, f.rightDoubleSpTime, 0.0) // idx 37
    }
    @Test fun stripsNewline() {
        val raw = (0 until 38).joinToString(",") { it.toString() } + "\n"
        assertNotNull(InsoleFrameParser.parse(raw))
    }
}
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**

```kotlin
// InsoleFrame.kt
package com.sarcopenianus.collector.core

data class InsoleFrame(
    val lp1: Double, val lp2: Double, val lp3: Double, val lp4: Double, val lp5: Double,
    val lp6: Double, val lp7: Double, val lp8: Double, val lp9: Double,
    val ax: Double, val ay: Double, val az: Double, val gx: Double, val gy: Double, val gz: Double,
    val leftStepSize: Double, val leftSpeed: Double, val leftSingleSpTime: Double, val leftDoubleSpTime: Double,
    val rp1: Double, val rp2: Double, val rp3: Double, val rp4: Double, val rp5: Double,
    val rp6: Double, val rp7: Double, val rp8: Double, val rp9: Double,
    val rightAx: Double, val rightAy: Double, val rightAz: Double,
    val rightGx: Double, val rightGy: Double, val rightGz: Double,
    val rightStepSize: Double, val rightSpeed: Double, val rightSingleSpTime: Double, val rightDoubleSpTime: Double
)
```
```kotlin
// InsoleFrameParser.kt
package com.sarcopenianus.collector.core

object InsoleFrameParser {
    fun parse(raw: String): InsoleFrame? {
        val a = raw.split(",").map { it.replace("\n", "") }
        if (a.size != 38) return null
        fun n(i: Int) = a[i].toDoubleOrNull() ?: Double.NaN
        return InsoleFrame(
            n(0), n(1), n(2), n(3), n(4), n(5), n(6), n(7), n(8),
            n(9), n(10), n(11), n(12), n(13), n(14),
            n(15), n(16), n(17), n(18),
            n(19), n(20), n(21), n(22), n(23), n(24), n(25), n(26), n(27),
            n(28), n(29), n(30), n(31), n(32), n(33),
            n(34), n(35), n(36), n(37)
        )
    }
}
```

- [ ] **Step 4: 跑绿**
- [ ] **Step 5: Commit**

### Task 2.3: ApiShape（DTO↔UI 形状映射）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/data/net/ApiShape.kt`（依赖 Task 3.1 的 DTO；本任务可先定义其消费的轻量 UI 模型，与 DTO 在 3.1 对接）
- Test: `app/src/test/java/.../data/net/ApiShapeTest.kt`

> 顺序提示：本任务的纯映射函数依赖 3.1 的 DTO 类型。若按线性执行，可将本任务并入 Phase 3 之后；这里保留在 Phase 2 是因其为纯逻辑。实现时先完成 3.1 的 DTO 定义再写本任务。

对照 `utils/apiShape.js`：`normalizePatient`（subject_id→subjectId、last_collected_at→lastAt 毫秒、existed 布尔）、`buildRawDataPayload`（patient_id + 38 命名字段）、`mapHistoryItem`（collected_at→ms、p1..p9→pressure[]、step_length 等驼峰、transformed→t）。

- [ ] **Step 1: 写失败测试**（含 last_collected_at ISO→毫秒、缺失→null；pressure 数组顺序）— 用具体 DTO 实例断言映射结果。
- [ ] **Step 2: 跑红 → Step 3: 实现纯映射函数 → Step 4: 跑绿 → Step 5: Commit**

（实现代码在 3.1 DTO 定稿后填入：每个映射为无副作用函数，字段一一对应旧 JS。）

### Task 2.4: TerminalCode（终端码生成）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/core/TerminalCode.kt`
- Test: `.../core/TerminalCodeTest.kt`

对照 `utils/terminal.js`：v4-UUID 形状 `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`，注入 rng 便于单测。

- [ ] **Step 1: 写失败测试**

```kotlin
package com.sarcopenianus.collector.core
import org.junit.Assert.*
import org.junit.Test

class TerminalCodeTest {
    @Test fun shape_matchesV4() {
        val code = TerminalCode.generate { 0.5 }
        val re = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        assertTrue(code, re.matches(code))
    }
}
```

- [ ] **Step 2: 跑红**
- [ ] **Step 3: 实现**

```kotlin
package com.sarcopenianus.collector.core

object TerminalCode {
    fun generate(rng: () -> Double = Math::random): String {
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".map { c ->
            if (c != 'x' && c != 'y') return@map c
            val r = (rng() * 16).toInt()
            val v = if (c == 'x') r else (r and 0x3) or 0x8
            v.toString(16).first()
        }.joinToString("")
    }
}
```

- [ ] **Step 4: 跑绿 → Step 5: Commit**

### Task 2.5: PatientLogic（校验/脱敏/搜索/编号）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/core/PatientLogic.kt`
- Test: `.../core/PatientLogicTest.kt`

对照 `utils/patient.js`：`formatSubjectId`(#00001)、`nextSeq`、`maskPhone`(138****6543，非 11 位原样)、`isValidPhone`(`^1\d{10}$`)、`validatePatient`(返回 ok/msg)、`searchPatients`(姓名/手机/编号匹配)。搜索消费一个轻量 `PatientUi`（含 name/phone/subjectId/seq）。

- [ ] **Step 1: 写失败测试**（覆盖：编号补零、脱敏边界、手机校验真假、搜索按姓名/手机数字/编号 # 命中）
- [ ] **Step 2: 跑红 → Step 3: 实现（逐函数对照 JS）→ Step 4: 跑绿 → Step 5: Commit**

```kotlin
package com.sarcopenianus.collector.core

data class PatientUi(
    val id: Int? = null, val subjectId: String = "", val name: String = "",
    val phone: String = "", val gender: String = "", val age: String = "",
    val lastAt: Long? = null, val seq: Int = 0, val existed: Boolean = false
)

object PatientLogic {
    fun formatSubjectId(seq: Int): String = "#" + seq.coerceAtLeast(0).toString().padStart(5, '0')
    fun nextSeq(patients: List<PatientUi>): Int = (patients.maxOfOrNull { it.seq } ?: 0) + 1
    fun maskPhone(phone: String?): String {
        val s = (phone ?: "").replace(Regex("\\s"), "")
        return if (s.length != 11) s else s.substring(0, 3) + "****" + s.substring(7)
    }
    fun isValidPhone(phone: String?): Boolean = Regex("^1\\d{10}$").matches((phone ?: "").trim())
    data class Validation(val ok: Boolean, val msg: String)
    fun validatePatient(name: String?, phone: String?): Validation {
        if (name.isNullOrBlank()) return Validation(false, "请输入患者姓名")
        if (!isValidPhone(phone)) return Validation(false, "请输入正确的 11 位手机号")
        return Validation(true, "")
    }
    fun searchPatients(patients: List<PatientUi>, keyword: String?): List<PatientUi> {
        val k = (keyword ?: "").trim().lowercase()
        if (k.isEmpty()) return patients
        val kd = k.replace(Regex("[^0-9]"), "")
        return patients.filter { p ->
            val name = p.name.lowercase()
            val id = (p.subjectId.ifEmpty { formatSubjectId(p.seq) }).lowercase()
            val idDigits = id.replace(Regex("[^0-9]"), "")
            name.contains(k) ||
                (kd.isNotEmpty() && p.phone.contains(kd)) ||
                id.contains(k) ||
                (kd.isNotEmpty() && idDigits.contains(kd))
        }
    }
}
```

---

## Phase 3 — 网络层（后端契约不变）

### Task 3.1: DTO + Retrofit 接口 + 信封

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/data/net/ApiModels.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/data/net/ApiService.kt`

对照 `api/*.js` 与 `request.js`：响应信封 `{ code|status, msg, data }`；接口路径/方法/字段如下。

- [ ] **Step 1: ApiModels.kt（DTO + 信封）**

```kotlin
package com.sarcopenianus.collector.data.net
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable data class ApiEnvelope<T>(
    val code: Int? = null, val status: Int? = null,
    val msg: String? = null, val data: T? = null
) { val effectiveCode: Int get() = code ?: status ?: 0 }

@Serializable data class EnableReq(
    val hospital: String, val dept: String, val name: String,
    val phone: String, @SerialName("terminal_code") val terminalCode: String, val passcode: String
)
@Serializable data class LoginReq(
    val phone: String, @SerialName("terminal_code") val terminalCode: String, val passcode: String
)
@Serializable data class Clinician(val id: Int, val hospital: String? = null,
    val dept: String? = null, val name: String? = null, val phone: String? = null)
@Serializable data class AuthResp(val token: String, val clinician: Clinician)

@Serializable data class PatientDto(
    val id: Int, @SerialName("subject_id") val subjectId: String? = null,
    val name: String? = null, val phone: String? = null, val gender: String? = null,
    val age: Int? = null, @SerialName("last_collected_at") val lastCollectedAt: String? = null,
    val existed: Boolean? = null
)
@Serializable data class CreatePatientReq(
    val name: String, val phone: String, val gender: String, val age: String
)
@Serializable data class HistoryItemDto(
    val id: Int? = null, val foot: String? = null,
    @SerialName("collected_at") val collectedAt: String? = null,
    val p1: Double? = null, val p2: Double? = null, val p3: Double? = null,
    val p4: Double? = null, val p5: Double? = null, val p6: Double? = null,
    val p7: Double? = null, val p8: Double? = null, val p9: Double? = null,
    val ax: Double? = null, val ay: Double? = null, val az: Double? = null,
    val gx: Double? = null, val gy: Double? = null, val gz: Double? = null,
    @SerialName("step_length") val stepLength: Double? = null,
    @SerialName("walking_speed") val walkingSpeed: Double? = null,
    @SerialName("single_support_time") val singleSupportTime: Double? = null,
    @SerialName("double_support_time") val doubleSupportTime: Double? = null
)
@Serializable data class HistoryResp(val items: List<HistoryItemDto> = emptyList())
@Serializable data class DeviceDto(
    val id: Int, @SerialName("device_code") val deviceCode: String,
    @SerialName("device_name") val deviceName: String? = null,
    val frequency: String? = null, @SerialName("is_enabled") val isEnabled: Boolean? = null
)
@Serializable data class RegisterDeviceReq(
    @SerialName("device_code") val deviceCode: String,
    @SerialName("device_name") val deviceName: String? = null
)
```

- [ ] **Step 2: ApiService.kt（Retrofit 接口，路径对齐旧 api/*.js）**

```kotlin
package com.sarcopenianus.collector.data.net
import retrofit2.http.*

interface ApiService {
    @POST("/clinician/enable") suspend fun enable(@Body b: EnableReq): ApiEnvelope<AuthResp>
    @POST("/clinician/login") suspend fun login(@Body b: LoginReq): ApiEnvelope<AuthResp>
    @GET("/clinician/me") suspend fun me(): ApiEnvelope<Clinician>
    @PUT("/clinician/me") suspend fun updateMe(@Body b: Map<String, String>): ApiEnvelope<Clinician>

    @GET("/patients") suspend fun listPatients(): ApiEnvelope<List<PatientDto>>
    @POST("/patients") suspend fun createPatient(@Body b: CreatePatientReq): ApiEnvelope<PatientDto>
    @GET("/patients/{id}") suspend fun getPatient(@Path("id") id: Int): ApiEnvelope<PatientDto>
    @GET("/patients/{id}/data") suspend fun history(
        @Path("id") id: Int, @QueryMap params: Map<String, String>
    ): ApiEnvelope<HistoryResp>

    @GET("/devices") suspend fun listDevices(): ApiEnvelope<List<DeviceDto>>
    @POST("/devices") suspend fun registerDevice(@Body b: RegisterDeviceReq): ApiEnvelope<DeviceDto>
    @DELETE("/devices/{id}") suspend fun deleteDevice(@Path("id") id: Int): ApiEnvelope<Unit>
    @POST("/devices/{code}/raw_data") suspend fun uploadRaw(
        @Path("code") code: String, @Body body: Map<String, @JvmSuppressWildcards Any?>
    ): ApiEnvelope<Unit>
}
```

- [ ] **Step 3: 回填 Task 2.3 的 ApiShape**（用上面 DTO 实现 normalizePatient / mapHistoryItem / buildRawDataPayload，并让 2.3 测试通过）。
- [ ] **Step 4: 编译** — `.\gradlew.bat :app:compileDebugKotlin` → SUCCESS。
- [ ] **Step 5: Commit**

### Task 3.2: 网络装配 + 鉴权拦截器（Bearer + 401 静默重试）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/data/net/Network.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/data/net/AuthInterceptor.kt`

对照 `request.js`：baseURL `https://api.sarcopenianus.com`、timeout 30s、`Content-Type: application/json;charset=UTF-8`、token 存「Bearer xxx」整串、无 token 仅放行 enable/login、其余无 token 取消、401 用 phone+terminalCode+passcode 调 login 换 token 重试一次（标记防循环）。

- [ ] **Step 1: AuthInterceptor.kt**

```kotlin
package com.sarcopenianus.collector.data.net
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(
    private val tokenProvider: () -> String?,        // 返回 "Bearer xxx" 或 null
    private val refresh: () -> String?               // 同步换新 token，失败返回 null
) : Interceptor {
    private val noAuth = listOf("/clinician/enable", "/clinician/login")
    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request()
        val path = req.url.encodedPath
        val needAuth = noAuth.none { path.contains(it) }
        val token = tokenProvider()
        if (token == null && needAuth) {
            // 无 token 的受保护请求：静默取消（对齐旧策略，不登出）
            throw java.io.IOException("no-token-cancel")
        }
        val authed = if (token != null) req.newBuilder().header("Authorization", token).build() else req
        var resp = chain.proceed(authed)
        // 401：HTTP 401 或后端 body code=401 都可能；此处仅处理 HTTP 层，body 层在 Repository 兜底重试
        if (resp.code == 401 && needAuth) {
            resp.close()
            val fresh = refresh() ?: return chain.proceed(authed)
            val retried = req.newBuilder().header("Authorization", fresh).build()
            resp = chain.proceed(retried)
        }
        return resp
    }
}
```

> 说明：后端把业务错误放在 body 的 `code` 字段（HTTP 仍 200），故 body 层 401 的静默重试在 Repository 调用处统一封装（见 5.1 的 `withAuthRetry`）。拦截器只兜 HTTP 401。

- [ ] **Step 2: Network.kt（单例装配，token/refresh 由 LocalStore + OperatorRepository 注入）**

```kotlin
package com.sarcopenianus.collector.data.net
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import java.util.concurrent.TimeUnit

object Network {
    const val BASE_URL = "https://api.sarcopenianus.com"
    private val json = Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true }

    fun create(tokenProvider: () -> String?, refresh: () -> String?): ApiService {
        val client = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .addInterceptor(AuthInterceptor(tokenProvider, refresh))
            .build()
        return Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(ApiService::class.java)
    }
}
```

- [ ] **Step 3: 编译** → SUCCESS。
- [ ] **Step 4: Commit**

---

## Phase 4 — 本地持久化

### Task 4.1: LocalStore（DataStore 封装）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/data/local/LocalStore.kt`

对照 `utils/clinicStorage.js`/`auth.js`/`terminal.js`：键 operator、patients、currentPatientId、token、terminalCode。operator/patients 用 JSON 序列化存字符串。`unlocked` 不持久化（在 VM 内存态）。

- [ ] **Step 1: 实现**

```kotlin
package com.sarcopenianus.collector.data.local
import android.content.Context
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import com.sarcopenianus.collector.core.TerminalCode
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

private val Context.ds by preferencesDataStore("clinic")

class LocalStore(private val ctx: Context) {
    private object K {
        val OPERATOR = stringPreferencesKey("__operator__")
        val PATIENTS = stringPreferencesKey("__patients__")
        val CURRENT = intPreferencesKey("__current_patient_id__")
        val TOKEN = stringPreferencesKey("__token__")
        val TERMINAL = stringPreferencesKey("__terminal_code__")
    }
    // 同步读（OkHttp 拦截器需要同步取 token）；写用挂起
    fun tokenBlocking(): String? = runBlocking { ctx.ds.data.first()[K.TOKEN] }
    suspend fun setToken(v: String) = edit { it[K.TOKEN] = v }
    suspend fun getOperatorJson(): String? = ctx.ds.data.first()[K.OPERATOR]
    suspend fun setOperatorJson(v: String) = edit { it[K.OPERATOR] = v }
    suspend fun clearOperator() = edit { it.remove(K.OPERATOR); it.remove(K.TOKEN) }
    suspend fun getPatientsJson(): String? = ctx.ds.data.first()[K.PATIENTS]
    suspend fun setPatientsJson(v: String) = edit { it[K.PATIENTS] = v }
    suspend fun getCurrentId(): Int? = ctx.ds.data.first()[K.CURRENT]
    suspend fun setCurrentId(id: Int) = edit { it[K.CURRENT] = id }
    suspend fun clearCurrentId() = edit { it.remove(K.CURRENT) }
    suspend fun terminalCode(): String {
        val cur = ctx.ds.data.first()[K.TERMINAL]
        if (cur != null) return cur
        val code = TerminalCode.generate()
        edit { it[K.TERMINAL] = code }
        return code
    }
    private suspend fun edit(block: (MutablePreferences) -> Unit) { ctx.ds.edit(block) }
}
```

- [ ] **Step 2: 编译** → SUCCESS。
- [ ] **Step 3: Commit**

---

## Phase 5 — Repository + ViewModel

### Task 5.1: OperatorRepository + OperatorViewModel

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/domain/OperatorRepository.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/vm/OperatorViewModel.kt`

对照 `store/modules/operator.js`：`enable`(生成 terminalCode→/enable→存 Bearer token+本地档案)、`unlock`(本地口令比对，内存态)、`refreshToken`(/login 换 token)、`me`、`reset`、`attribution`。body 层 401 静默重试封装 `withAuthRetry`（响应 code==401 时调 refresh 再跑一次原 suspend 块）。

- [ ] **Step 1: OperatorRepository.kt**

```kotlin
package com.sarcopenianus.collector.domain
import com.sarcopenianus.collector.core.TerminalCode
import com.sarcopenianus.collector.data.local.LocalStore
import com.sarcopenianus.collector.data.net.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable data class Operator(
    val hospital: String = "", val dept: String = "", val name: String = "",
    val phone: String = "", val passcode: String = "", val enabled: Boolean = false,
    val clinicianId: Int = 0, val terminalCode: String = ""
)

class OperatorRepository(private val local: LocalStore) {
    private val json = Json { ignoreUnknownKeys = true }
    lateinit var api: ApiService   // 由 AppContainer 注入（带拦截器）

    suspend fun loadOperator(): Operator? =
        local.getOperatorJson()?.let { runCatching { json.decodeFromString<Operator>(it) }.getOrNull() }

    suspend fun enable(hospital: String, dept: String, name: String, phone: String, passcode: String): Operator {
        val terminal = local.terminalCode()
        val res = api.enable(EnableReq(hospital, dept, name, phone, terminal, passcode))
        val auth = res.data!!
        local.setToken("Bearer ${auth.token}")
        val op = Operator(hospital, dept, name, phone, passcode, true, auth.clinician.id, terminal)
        local.setOperatorJson(json.encodeToString(Operator.serializer(), op))
        return op
    }

    // 静默换 token（拦截器 refresh 回调 & body 层 401 都用它）。同步签名供拦截器调用。
    fun refreshTokenBlocking(): String? = kotlinx.coroutines.runBlocking {
        val op = loadOperator() ?: return@runBlocking null
        if (op.passcode.isEmpty()) return@runBlocking null
        val res = runCatching {
            api.login(LoginReq(op.phone, op.terminalCode.ifEmpty { local.terminalCode() }, op.passcode))
        }.getOrNull() ?: return@runBlocking null
        val token = "Bearer ${res.data!!.token}"
        local.setToken(token)
        token
    }

    suspend fun me() = api.me().data
    suspend fun reset() = local.clearOperator()
}
```

- [ ] **Step 2: OperatorViewModel.kt（StateFlow 暴露 operator + unlocked 内存态）**

```kotlin
package com.sarcopenianus.collector.ui.vm
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sarcopenianus.collector.domain.Operator
import com.sarcopenianus.collector.domain.OperatorRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class OperatorViewModel(private val repo: OperatorRepository) : ViewModel() {
    private val _operator = MutableStateFlow<Operator?>(null)
    val operator = _operator.asStateFlow()
    private val _unlocked = MutableStateFlow(false)   // 内存态：每次启动需重新解锁
    val unlocked = _unlocked.asStateFlow()
    val isEnabled get() = _operator.value?.enabled == true

    init { viewModelScope.launch { _operator.value = repo.loadOperator() } }

    suspend fun enable(hospital: String, dept: String, name: String, phone: String, passcode: String) {
        _operator.value = repo.enable(hospital, dept, name, phone, passcode)
        _unlocked.value = true
    }
    fun unlock(passcode: String): Boolean {
        val ok = _operator.value?.passcode == passcode && passcode.isNotEmpty()
        if (ok) _unlocked.value = true
        return ok
    }
    fun reset() { viewModelScope.launch { repo.reset(); _operator.value = null; _unlocked.value = false } }
    fun attribution(): Triple<String, String, String> {
        val o = _operator.value
        return Triple(o?.hospital ?: "", o?.dept ?: "", o?.name ?: "")
    }
}
```

- [ ] **Step 3: 编译** → SUCCESS。
- [ ] **Step 4: Commit**

### Task 5.2: PatientRepository + PatientViewModel

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/domain/PatientRepository.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/vm/PatientViewModel.kt`

对照 `store/modules/patient.js`：`loadList`(/patients→normalizePatient→写缓存)、`create`(/patients→若 id 命中则替换→置顶→select)、`select`/`clearCurrent`、本地缓存按 lastAt 倒序 + `searchPatients` 过滤、`current`/`currentSubjectId` getter。历史拉取 `history(id, {page,page_size})`。

- [ ] **Step 1: PatientRepository.kt** — `listPatients()`/`createPatient()`/`history()` 调 api，结果经 ApiShape 映射为 `PatientUi`/历史 UI 模型；缓存读写经 LocalStore（JSON）。
- [ ] **Step 2: PatientViewModel.kt** — `patients: StateFlow<List<PatientUi>>`、`currentId: StateFlow<Int?>`、派生 `current`/`currentSubjectId`；`loadList()`、`create()`、`select()`、`list(keyword)` 用 `PatientLogic.searchPatients` + lastAt 倒序。init 从缓存恢复 patients + currentId。
- [ ] **Step 3: 编译 → Step 4: Commit**

（实现按上述契约逐方法对照 JS；列表排序：`sortedByDescending { it.lastAt ?: 0 }` 后过滤。）

### Task 5.3: BleRepository + BleViewModel（核心，1:1 译 blueTooth.js）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/domain/RealtimeModels.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/domain/BleRepository.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/vm/BleViewModel.kt`

对照 `store/modules/blueTooth.js` 全文，逐方法移植（调用 vendored `com.clj.fastble.BleManager`）：

- 初始化：`BleManager.getInstance().init(application)`。
- `isBluetoothOpen`/`syncBluetoothState`：`BleManager.isBlueEnable()`。
- 运行时权限 `requestBlePermissions`：Android 12+ 申请 `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT`；≤Android 11 申请 `ACCESS_FINE_LOCATION`（权限请求在 Activity/Compose 侧用 `rememberLauncherForActivityResult`，Repository 暴露所需权限清单 + 是否已授予查询）。
- `scanNearbyDevices`：`BleManager.scan(...)`；回调里按 MAC 去重、过滤无名、标记 added（在 deviceList 中）；写入 `discovered: StateFlow<List<DiscoveredDevice>>`、`isScanning`。
- `addScannedDevice`：调 Patient/Device api 注册（device_code=MAC）后刷新列表。
- `connectDevice(id)`：`BleManager.connect(mac, gattCallback)`；首连失败（onConnectFail）`retriesLeft=1` 自动重试一次；onConnectSuccess 后 `setMtu(512)`、发现服务取 `services[2]`、找 WRITE/NOTIFY 特征、`notify(...)`；掉线 onDisConnected 只复位、不自动重连。
- NOTIFY 回调：bytes→String→`InsoleFrameParser.parse`；非 38 丢弃；更新 `realtime` StateFlow；若有 currentPatientId 则 `api.uploadRaw(code, ApiShape.buildRawDataPayload(pid, frame))`，无患者跳过上传。
- `disconnectDevice`/`deleteDevice`/`getDevicesList`/`sendMassge(toHex)` 对照移植。

- [ ] **Step 1: RealtimeModels.kt**

```kotlin
package com.sarcopenianus.collector.domain

data class FootRealtime(
    val pressure: List<Double> = List(9) { 0.0 },
    val ax: Double? = null, val ay: Double? = null, val az: Double? = null,
    val gx: Double? = null, val gy: Double? = null, val gz: Double? = null,
    val speed: Double? = null, val length: Double? = null,
    val single: Double? = null, val double: Double? = null
)
data class Realtime(
    val hasData: Boolean = false,
    val left: FootRealtime = FootRealtime(),
    val right: FootRealtime = FootRealtime()
)
data class DiscoveredDevice(val name: String, val address: String, val rssi: Int?, val added: Boolean)
```

- [ ] **Step 2: BleRepository.kt** — 持有 `BleManager`、`bleDevices: Map<code, BleDevice>`、连接态/uuid 缓存；暴露 `realtime`/`discovered`/`isScanning`/`isBluetoothOpen`/`deviceList` 的 StateFlow；方法签名对照上面列表。NOTIFY 帧映射为 `Realtime`（左 pressure=lp1..lp9 + imu + 步态；右同）。
- [ ] **Step 3: BleViewModel.kt** — 转发 Repository 的 StateFlow，提供 `scan()/connect(id)/disconnect(id)/addScanned(d)/loadDevices()/deleteDevice(id)`；注入 currentPatientId provider（来自 PatientViewModel）。
- [ ] **Step 4: 编译** → SUCCESS（蓝牙逻辑真机验证留到 Phase 8）。
- [ ] **Step 5: Commit**

> 注：38 字段顺序、`services[2]`、MTU 512、GATT133 重试一次、掉线不重连——必须逐行对照 `blueTooth.js`，不得"优化"。

---

## Phase 6 — UI：主题与基础组件

### Task 6.1: 主题（令牌对照 tokens.scss）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/theme/Color.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/theme/Theme.kt`

- [ ] **Step 1: Color.kt（值对照 styles/tokens.scss）**

```kotlin
package com.sarcopenianus.collector.ui.theme
import androidx.compose.ui.graphics.Color

object Ca {
    val primary = Color(0xFF2F6DF6)
    val primaryLight = Color(0xFFE7F0FE)
    val success = Color(0xFF15A05A)
    val warning = Color(0xFFE8A33D)
    val danger = Color(0xFFE5484D)
    val bg = Color(0xFFF5F7FA)
    val border = Color(0xFFE6EBF2)
    val t1 = Color(0xFF0F172A)
    val t2 = Color(0xFF64748B)
    val t3 = Color(0xFF94A3B8)
    val white = Color(0xFFFFFFFF)
}
```

- [ ] **Step 2: Theme.kt** — `GaitTheme { content }` 用 `MaterialTheme(colorScheme=lightColorScheme(primary=Ca.primary, background=Ca.bg, ...))` 包裹，提供统一字体（系统默认即可，PingFang/Inter 在 Android 上回退系统中文字体）。
- [ ] **Step 3: 编译 → Step 4: Commit**

### Task 6.2: 基础组件（对照 components/base/Ca*.vue）

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/components/CaComponents.kt`

逐个移植，圆角/间距/字号对照各 .vue（rpx→dp 约定：750rpx=屏宽，取 `rpx/2` 近似 dp，圆角 28rpx≈14dp、24rpx≈12dp）：

- `CaCard(title?, content)` — 白底、1dp border `Ca.border`、圆角 14dp、padding 16dp、底边距 14dp、阴影；标题 14sp/700/`Ca.t1`。
- `CaInput(label, icon?, value, onValueChange, placeholder, password, type, required)` — 标签 12sp/`Ca.t2`（required 加红 *）；输入框白底圆角 12dp，左 emoji 图标；`password`→`PasswordVisualTransformation`，`type==number`→数字键盘。
- `CaEmpty(icon, title, desc, button?, onAction?)` — 居中，大 emoji（48sp，alpha .25）、标题 16sp/700、描述 13sp/`Ca.t3`。
- `CaMetric(label, value, unit?, left?, right?)` — 白卡，值 22sp/700，左右小字。
- `CaStatusStrip(title, sub)` — 橙色条 `#FDF2E2`/border `#F3DCB4`，脉冲圆点 `Ca.warning`，文字棕色 `#A96A12`/`#B5853A`。
- `CaPatientBar(current?, onSwitch)` — 头像方块（首字）、姓名 + subjectId·性别·年龄、右侧「切换 ⇄」；无患者显示「未选择患者 / 点此选择患者」。点击导航到 patient/select。

- [ ] **Step 1: 实现全部组件**（每个为 `@Composable`，参数如上；样式值对照 .vue）。
- [ ] **Step 2: 编译 → Step 3: Commit**

---

## Phase 7 — UI：屏幕与导航

### Task 7.1: 导航图 + 启动网关 + 底部 Tab

**Files:**
- Create: `app/src/main/java/com/sarcopenianus/collector/ui/nav/AppNav.kt`
- Modify: `app/src/main/java/com/sarcopenianus/collector/MainActivity.kt`
- Create: `app/src/main/java/com/sarcopenianus/collector/AppContainer.kt`（手动 DI：装配 LocalStore/Network/Repos/VM 工厂）

对照 `App.vue onLaunch` 网关 + `pages.json`（3 Tab + 4 普通页）。

- [ ] **Step 1: AppContainer.kt** — 单例持有 `LocalStore`；先建 `OperatorRepository`，用其 `refreshTokenBlocking` + `local.tokenBlocking` 装配 `Network.create(...)` 得 `ApiService`，回注各 Repository.api；提供 ViewModel 工厂。
- [ ] **Step 2: AppNav.kt** — `NavHost`，路由：`enable`/`unlock`/`patient_select`/`patient_new`/`main`(含底部 Tab：`home`/`data`/`mine`)。启动决策（在根 Composable）：
  - `!isEnabled` → `enable`
  - 已启用 `!unlocked` → `unlock`
  - 已解锁 `current==null` → `patient_select`
  - 否则 → `main`(home)
- [ ] **Step 3: MainActivity** — `setContent { GaitTheme { AppRoot() } }`，`AppRoot` 收集 operator/patient StateFlow 决定起始路由；底部导航 3 Tab（首页/数据/我的，图标可用 Material 图标占位或复用旧 tabbar png）。
- [ ] **Step 4: 编译 + 真机** — 启动进入 enable 页（首次）。
- [ ] **Step 5: Commit**

### Task 7.2: EnableScreen（对照 pages/setup/enable.vue）

**Files:** Create `ui/screens/EnableScreen.kt`

- [ ] **Step 1: 实现** — Hero(🦶 + 「步态采集系统」+「首次注册 · 请填写本机操作信息」)；5 个 `CaInput`：医院🏥、科室🩺、医生姓名👤、联系方式📞(number)、设置口令🔒(password)；按钮「注册并启用本机」；hint 两行说明。
  - 校验（对照 enable.vue:24-27）：医院/科室/姓名非空；`PatientLogic.isValidPhone`；口令≥4 位。失败 Toast（Compose 用 SnackbarHost 或简单 Toast）。
  - 成功：`operatorVm.enable(...)` 后导航 `patient_select`；失败提示「启用失败：请检查网络后重试」。
- [ ] **Step 2: 真机过目 → Step 3: Commit**

### Task 7.3: UnlockScreen（对照 pages/setup/unlock.vue）

**Files:** Create `ui/screens/UnlockScreen.kt`

- [ ] **Step 1: 实现** — Hero + subtitle(医院·科室·姓名)；口令 `CaInput`(password)；「解锁」按钮；hint「非本人？重新启用本机」(可点)。
  - `operatorVm.unlock(passcode)`：失败 Toast「口令错误」；成功若 `current!=null`→`main(home)`，否则→`patient_select`。
  - 重新启用：确认对话框 → `operatorVm.reset()` → `enable`。
- [ ] **Step 2: 真机过目 → Step 3: Commit**

### Task 7.4: PatientSelectScreen（对照 pages/patient/select.vue）

**Files:** Create `ui/screens/PatientSelectScreen.kt`

- [ ] **Step 1: 实现** — 搜索框(🔍, 绑定 kw)；「＋新建患者」虚线按钮→`patient_new`；列表头「最近采集 / 共 N 人」；空态 `CaEmpty`；患者 cell(首字头像 + 姓名 + 脱敏手机 + 「subjectId · 最近 MM-DD」+ ›)。
  - 进入时 `patientVm.loadList()`（失败用本地缓存）；列表 = `patientVm.list(kw)`；点击 `select(id)` → `main(home)`。
- [ ] **Step 2: 真机过目 → Step 3: Commit**

### Task 7.5: PatientNewScreen（对照 pages/patient/new.vue）

**Files:** Create `ui/screens/PatientNewScreen.kt`

- [ ] **Step 1: 实现** — 姓名👤(required)、手机📞(required,number)；性别分段(男/女)；年龄(number)；「患者编号 创建后由系统自动派发 / 导出科研只用此编号」说明；按钮「创建并设为当前患者」；hint。
  - 校验 `PatientLogic.validatePatient`；`patientVm.create(...)`；若返回 `existed` 提示「该患者已存在，已为你选中」；成功 → `main(home)`。
- [ ] **Step 2: 真机过目 → Step 3: Commit**

### Task 7.6: HomeScreen（足底热力图 + IMU + 实时参数，对照 pages/home/home.vue）

**Files:** Create `ui/screens/HomeScreen.kt`

热力点位坐标 1:1 移植自 home.vue:54-69（左脚百分比，右脚 x 镜像 `100-x`）：
左脚 [(37,8),(37,32),(29,30),(22,28),(34,52),(18,45),(34,64),(29,78),(29,86)]。

- [ ] **Step 1: 实现**

要点（对照 home.vue）：
- 顶部 `CaPatientBar`。
- 足图卡：`Box`，背景 `Image(painterResource(R.drawable.foot))`（contain, 居中）；上叠 18 个点（左 9 + 右 9），每点用 `Box`+`offset` 按百分比定位（`offset(x = (pctX/100f*W).dp, y=...)`，或在 `BoxWithConstraints` 内按 maxWidth/Height 计算）；点直径 17dp、圆形、填充 `FootMetrics.shade(adc)`、中心叠 ADC 整数文字（8sp/白/700）；无实时帧时文字空、颜色按 0。
- IMU 折叠卡：标题「IMU 原始数据」+ ▸/▾；展开显示左/右脚 加速度 ax/ay/az、角速度 gx/gy/gz（2 位小数，`'-'` 兜底）。
- 「实时参数」标题 + 2×2 `CaMetric`：步速(m/s)、步长(cm, 经 `mToCm`)、单支撑(s)、双支撑(s)，各带左/右值与左右均值（`fmt`/`mean` 对照 home.vue:81-104）；`hasData==false` 时整块用 `CaEmpty(👣,...)`。
- 数据源：`bleVm.realtime` 用 `collectAsStateWithLifecycle()`。
- [ ] **Step 2: 真机过目（连接采集时验证）→ Step 3: Commit**

### Task 7.7: DataScreen（分段 + KPI + 图表，对照 pages/data/data.vue）

**Files:** Create `ui/screens/DataScreen.kt`

图表用自绘 Canvas（数据量小：折线 ≤20 点、柱状 2 项），不引第三方图表库。计算逻辑 1:1 对照 data.vue（rangeBounds 本周/上周/本月/近半年、framesInRange、kpis、lineData 按 collectedAt 分组取左右平均最近 20、pressureData 左右 9 路压力和均值、singleData 左右单支撑均值）。

- [ ] **Step 1: 把 data.vue 的纯计算抽成可单测 Kotlin**（`DataAggregation.kt` + 测试：rangeBounds 边界、framesInRange 过滤、kpis 均值、按脚 L/R 聚合）。先写失败测试 → 实现 → 跑绿。
- [ ] **Step 2: 实现 DataScreen** — `CaPatientBar`；分段控件(本周/上周/本月/近半年)；`hasData` 时显示 4 KPI 卡 + 3 个 `CaCard`(步速趋势折线 / 左右脚压力对比柱 / 单支撑柱)，自绘 Canvas；空态 `CaEmpty(📊,...)`。`onShow` 等价：进入/恢复时 `patientVm` 取当前 id 调 `history(id,{page:1,page_size:200})`。
- [ ] **Step 3: 真机过目 → Step 4: Commit**

### Task 7.8: MineScreen（操作员 + 设备管理 + 扫描弹窗，对照 pages/mine/mine.vue）

**Files:** Create `ui/screens/MineScreen.kt`

- [ ] **Step 1: 实现**
- `CaPatientBar` + 归属条「本次采集归属：医院·科室·医生」(绿底)。
- 采集中 `CaStatusStrip`（以有已连接设备近似；副标题列已连接设备名）。
- 「操作员信息」`CaCard`：医院/科室/医生/联系方式 4 行 + 「重新启用本机」(红, 确认对话框→reset→enable)。
- 提示条（notice）：「如需连接设备，请点『+ 新增设备』…」。
- 「设备列表」`CaCard`：右上「+ 新增设备」→打开扫描底部弹窗；设备 cell（名/状态标签 已连接绿·未连接灰/device_code/「连接」或「断开连接」+「删除」，操作前确认对话框）；空态 `CaEmpty(📡,...)`。
- 扫描底部弹窗(`ModalBottomSheet`)：标题 + 重新扫描；扫描中/无结果提示；`discovered` 列表(名/MAC·dBm/「添加」或「已添加」)；底部 重新扫描/关闭。打开前用 `bleVm.syncBluetoothState()` 判断蓝牙开关；扫描前申请运行时权限（`rememberLauncherForActivityResult` 申请 Task 5.3 暴露的权限清单）。
- 进入/恢复时 `bleVm.loadDevices()`；可保留 5s 轮询（对照 mine.vue:130）。
- [ ] **Step 2: 真机过目（搜索/连接/删除）→ Step 3: Commit**

---

## Phase 8 — 真机回归（手动，无代码）

### Task 8.1: 全流程真机回归清单

- [ ] **Step 1:** 构建 release/debug 装真机：`.\gradlew.bat :app:assembleDebug` + adb install。
- [ ] **Step 2: 走查（对照旧工程真机清单）**
  - 首次启动 → enable 页；填表启用 → 落 RDS（clinicians/patients 链路）→ 进 patient_select。
  - 杀进程重开 → 因 unlocked 内存态，回到 unlock 页；口令解锁。
  - 新建/选择患者 → 进首页。
  - 我的页「+新增设备」→ 蓝牙搜索附近设备（验证权限申请弹窗）→ 添加 → 列表出现。
  - 连接鞋垫 → 首页足图随按压变色显数、IMU 卡展开见 6 轴、步速/步长(cm) 实时；采集帧上传落库（查 `device_raw_data` 每帧 L/R 两行 + `device_transformed_data` T 值 + `patients.last_collected_at`）。
  - 数据页按当前患者拉历史 → KPI/趋势/对比图显示；切换时间分段正确。
  - 断开连接 → 首页归零空态；未选患者时采集不上传。
  - 弱网/越权 → 数据页空态、不崩溃；token 过期 → 静默换 token 重试，无登录页弹出。
- [ ] **Step 3:** 记录问题，逐项回到对应 Task 修复。
- [ ] **Step 4: Commit**（如有修复）

---

## 风险与对照纪律

1. **38 字段顺序硬编码**：以硬件文档为准，逐字段对照 `blueTooth.js`，改前与硬件团队核对。
2. **真机 GATT 行为**：连接重试/MTU/notify 仅能真机验证（Phase 8）。
3. **foot.png 点位坐标**：1:1 用 home.vue 百分比，右脚 x 镜像。
4. **AGP/Gradle/Compose 版本**：若 Studio 同步报不兼容，升到最近稳定一致组合并回写本计划版本号。
5. **付费加密插件**：只取开源 fastble 底层，不碰 `index.uts`/`BleHelper.kt`。
6. **后端零改动**：所有接口路径/字段保持现状；仅客户端重写。
