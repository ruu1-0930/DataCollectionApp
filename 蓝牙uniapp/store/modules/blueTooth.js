import { defineStore } from 'pinia'
import { store } from '@/store'
import { listDevicesApi, registerDeviceApi, deleteDeviceApi as deleteDeviceApiReq, createCollectionApi, uploadCollectionBatchApi, stopCollectionApi } from '@/api'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { useOperatorStoreWithOut } from '@/store/modules/operator'
import { createBleLines, parseTelemetry } from '@/utils/bleTelemetry'
import { createCollectionSession } from '@/utils/collectionSession'
import { createTelemetryQueue } from '@/utils/telemetryQueue'
import { BleLib } from '@/uni_modules/android-ble'

const collectionRuntimes = new WeakMap()
const collectionStorageKey = 'collection_queue_v1'

const mapper = {
  10000: '未初始化蓝牙适配器',
  10001: '当前蓝牙适配器不可用',
  10002: '没有找到指定设备',
  10003: '连接失败',
  10004: '没有找到指定服务',
  10005: '没有找到指定特征值',
  10006: '当前连接已断开',
  10007: '当前特征值不支持此操作',
  10008: '其余所有系统上报的异常',
  10009: 'Android 系统特有，系统版本低于 4.3 不支持 BLE',
  10010: '已连接',
  10011: '配对设备需要配对码',
  10012: '连接超时',
  10013: '连接 deviceId 为空或者是格式不正确'
}

const storage_device_key = '_deviceList_'

// realtime 初始空态（断开/未采集时）：压力全 0、IMU/参数为 '-'
function emptyRealtime() {
  const foot = () => ({
    pressure: [0, 0, 0, 0, 0, 0, 0, 0, 0],
    imu: { ax: '-', ay: '-', az: '-', gx: '-', gy: '-', gz: '-' },
    speed: '-', length: '-', single: '-', double: '-'
  })
  return { hasData: false, left: foot(), right: foot() }
}

export const useBlueToothStore = defineStore('blueToothStore', {
  state: () => {
    return {
      // 蓝牙是否开启
      isBluetoothOpen: false,
      // 全局蓝牙对象
      globalBle: new BleLib(),

      // 多设备开发 初始化对象
      bles_objs: {
        // '18:8B:0E:CC:81:BD': {
        //   // 蓝牙对象
        //   ble: new BleLib(),
        //   // 是否连接
        //   isConnected: false,
        //   // 服务uuid
        //   service_uuid: '',
        //   // 特征值uuid 写
        //   write_characteristic_uuid: '',
        //   // 特征值uuid 读
        //   read_characteristic_uuid: ''
        // }
      },
      // 设备列表
      deviceList: [],

      // 新增设备：蓝牙扫描到的附近设备（按 MAC 去重，临时态）
      discovered: [],
      // 是否正在扫描
      isScanning: false,

      // 最近一帧实时步态（仅供首页展示，不落库；落库走后端拆分）
      realtime: emptyRealtime(),
      gpsRealtime: null,
      collectionState: { active: null, reason: '', rejected: 0, waiting: false,
        queue: { pending: 0, sessions: 0, sending: false, paused: false, error: '' } }
    }
  },
  getters: {},
  actions: {
    ensureCollection() {
      if (collectionRuntimes.has(this)) return collectionRuntimes.get(this)
      const identity = () => {
        const op = useOperatorStoreWithOut()
        return { clinicianId: op.operator?.clinicianId, authEpoch: op.authRuntime.authEpoch, unlocked: op.unlocked }
      }
      const runtime = { uploadTimer: null }
      collectionRuntimes.set(this, runtime)
      runtime.queue = createTelemetryQueue({
        load: () => uni.getStorageSync(collectionStorageKey),
        save: value => uni.setStorageSync(collectionStorageKey, value),
        identity,
        api: { create: createCollectionApi, batch: uploadCollectionBatchApi, stop: stopCollectionApi },
        onChange: value => { this.collectionState.queue = value },
      })
      this.collectionState.queue = runtime.queue.snapshot()
      runtime.session = createCollectionSession({ queue: runtime.queue, identity,
        onChange: value => {
          this.collectionState.active = value.active
          this.collectionState.reason = value.reason
          if (typeof uni.setKeepScreenOn === 'function') uni.setKeepScreenOn({ keepScreenOn: !!value.active })
          if (value.reason === 'background') uni.showToast({ title: 'App已离开前台，采集已停止，待上传数据已保留', icon: 'none', duration: 3000 })
          if (value.reason === 'storage' || value.reason === 'capacity' || value.reason === 'clock_rollback') {
            uni.showToast({ title: value.reason === 'clock_rollback' ? '手机时间回退，已停止采集，请校准时间' : '本地缓存不可用或已满，已停止采集', icon: 'none', duration: 3000 })
          }
        },
      })
      return runtime
    },
    scheduleCollectionUpload(delay = 1000) {
      const runtime = this.ensureCollection()
      if (runtime.uploadTimer !== null) return
      runtime.uploadTimer = setTimeout(async () => {
        runtime.uploadTimer = null
        await runtime.queue.drain()
        const status = runtime.queue.snapshot()
        if (status.pending && !status.paused) this.scheduleCollectionUpload()
      }, delay)
    },
    startCollection(deviceCode) {
      const runtime = this.ensureCollection()
      const ps = usePatientStoreWithOut()
      try {
        runtime.session.start({ patientId: ps.currentId, deviceCode, connected: !!this.bles_objs[deviceCode]?.isConnected })
        this.bles_objs[deviceCode]?.lineStream?.reset()
        this.collectionState.waiting = false
        this.scheduleCollectionUpload(0)
      } catch {
        uni.showToast({ title: '无法开始：请解锁、选择患者并连接设备，检查本地缓存', icon: 'none', duration: 3000 })
      }
    },
    stopCollection(reason = 'user') {
      const code = this.collectionState.active?.device_code
      this.ensureCollection().session.stop(reason)
      if (code) this.bles_objs[code]?.lineStream?.reset()
      this.collectionState.waiting = false
      this.scheduleCollectionUpload(0)
    },
    retryCollectionUpload() { return this.ensureCollection().queue.drain(true) },
    endCollectionContext(reason = 'identity') {
      this.stopCollection(reason)
      Object.keys(this.bles_objs).forEach(code => this.invalidateConnection(code, true))
      this.realtime = emptyRealtime()
      this.gpsRealtime = null
    },
    invalidateConnection(code, close = false) {
      const slot = this.bles_objs[code]
      if (!slot) return
      slot.connectionEpoch = (slot.connectionEpoch || 0) + 1
      slot.lineStream?.reset()
      slot.lineStream = null
      slot.isConnected = false
      slot.connecting = false
      if (this.collectionState.active?.device_code === code) this.collectionState.waiting = true
      clearTimeout(slot.connectTimer)
      clearTimeout(slot.retryTimer)
      if (close) {
        try {
          if (slot.service_uuid && slot.read_characteristic_uuid) slot.ble.onNotityReadBleData(slot.service_uuid, slot.read_characteristic_uuid, false, () => {})
        } catch { /* Some native callbacks can already be released on adapter shutdown. */ }
        try { slot.ble.close() } catch { /* JS generation fencing still rejects released callbacks. */ }
      }
    },
    acceptTelemetry(code, epoch, line, receivedAt) {
      const slot = this.bles_objs[code]
      if (!slot?.isConnected || slot.connectionEpoch !== epoch) return
      let parsed
      try { parsed = parseTelemetry(line) }
      catch { this.collectionState.rejected += 1; return }
      const runtime = this.ensureCollection()
      const active = runtime.session.active
      if (active && active.patient_id !== usePatientStoreWithOut().currentId) this.stopCollection('patient')
      if (parsed.stream === 'gps') this.gpsRealtime = { ...parsed.gps, receivedAt, deviceCode: code }
      else {
        const d = parsed.payload
        this.realtime = { hasData: true, deviceCode: code,
          left: { pressure: Array.from({ length: 9 }, (_, i) => d[`lp${i + 1}`]),
            imu: { ax: d.ax, ay: d.ay, az: d.az, gx: d.gx, gy: d.gy, gz: d.gz },
            speed: d.left_speed, length: d.left_step_size, single: d.left_single_sp_time, double: d.left_double_sp_time },
          right: { pressure: Array.from({ length: 9 }, (_, i) => d[`rp${i + 1}`]),
            imu: { ax: d.right_ax, ay: d.right_ay, az: d.right_az, gx: d.right_gx, gy: d.right_gy, gz: d.right_gz },
            speed: d.right_speed, length: d.right_step_size, single: d.right_single_sp_time, double: d.right_double_sp_time } }
      }
      runtime.session.receive(code, epoch, parsed, receivedAt)
      this.scheduleCollectionUpload()
    },
    // 实时同步系统蓝牙开关状态（initBle 的监听只在“切换”时触发，启动前已开启的情况要主动查一次）
    syncBluetoothState() {
      // #ifdef APP-PLUS
      try {
        this.isBluetoothOpen = this.globalBle.isEnabled()
      } catch (e) {
        this.isBluetoothOpen = false
      }
      // #endif
      return this.isBluetoothOpen
    },

    // 申请蓝牙扫描所需的 Android 运行时权限（旧代码从不扫描列表，故这些“危险权限”从未在运行时被授予）
    // Android 12+ 需 BLUETOOTH_SCAN/CONNECT；Android 11- 扫描需 ACCESS_FINE_LOCATION，一次性都申请。
    requestBlePermissions() {
      return new Promise((resolve) => {
        // #ifdef APP-PLUS
        if (uni.getSystemInfoSync().platform !== 'android') {
          resolve(true)
          return
        }
        try {
          plus.android.requestPermissions(
            ['android.permission.BLUETOOTH_SCAN', 'android.permission.BLUETOOTH_CONNECT', 'android.permission.ACCESS_FINE_LOCATION'],
            (res) => {
              // 不同 Android 版本要求的权限不同，拿到任意扫描相关权限即放行
              resolve((res.granted && res.granted.length > 0) || false)
            },
            () => {
              resolve(false)
            }
          )
        } catch (e) {
          resolve(true) // 异常时不阻塞，交给扫描结果兜底
        }
        // #endif
        // #ifndef APP-PLUS
        resolve(true)
        // #endif
      })
    },

    // 扫描附近蓝牙设备（durationMs 后原生自动停止），结果按 MAC 去重存入 discovered
    async scanNearbyDevices(durationMs = 6000) {
      // 用原生实时状态判断，避免依赖只在“切换”时更新的 isBluetoothOpen 旧值
      if (!this.syncBluetoothState()) {
        uni.showToast({ title: '请先打开手机蓝牙', icon: 'none' })
        return
      }

      // Android 扫描必须先拿到运行时权限，否则系统静默返回 0 个结果
      const granted = await this.requestBlePermissions()
      if (!granted) {
        this.isScanning = false
        uni.showToast({ title: '需授予蓝牙/定位权限才能搜索设备', icon: 'none', duration: 2500 })
        return
      }

      this.discovered = []
      this.isScanning = true
      const known = new Set(this.deviceList.map((d) => String(d.device_code).toUpperCase()))
      this.globalBle.startScanBleDevice(durationMs, (res) => {
        // 仅 type==0 是扫描结果帧，其余为错误/状态帧
        if (res?.type !== 0) {
          return
        }
        const d = res?.data?.device
        const mac = d?.address
        if (!mac) return // 无 MAC 不可连，跳过
        const name = d.name || d.alias || res?.data?.scanRecord?.deviceName || ''
        // 只展示有名字的设备（过滤海量无名广播），避免列表噪声
        if (!name) return
        const macU = String(mac).toUpperCase()
        if (this.discovered.some((x) => x.address.toUpperCase() === macU)) return
        this.discovered.push({
          name,
          address: mac,
          rssi: res?.data?.rssi ?? null,
          added: known.has(macU) // 是否已在设备列表
        })
      })
      // 原生扫描到时长后自停，这里同步收起“扫描中”态
      setTimeout(() => { this.isScanning = false }, durationMs)
    },

    // 把扫描到的设备登记到后端（device_code = MAC），成功后刷新列表，返回是否成功
    async addScannedDevice(dev) {
      if (!dev?.address) return false
      uni.showLoading({ title: '添加中', mask: true })
      try {
        await registerDeviceApi({ device_name: dev.name || dev.address, device_code: dev.address })
        await this.getDevicesList()
        uni.hideLoading()
        uni.showToast({ title: '添加设备成功', icon: 'success' })
        return true
      } catch (e) {
        uni.hideLoading()
        uni.showToast({ title: '添加失败：请检查网络', icon: 'none' })
        return false
      }
    },
    initBle() {
      this.globalBle.onBtOpenStateListener((res) => {
        this.isBluetoothOpen = res.data ? true : false

        if (!res.data) {
          this.endCollectionContext('bluetooth_off')
        }
      })
    },

    // 检测蓝牙是否开启
    checkBluetooth() {
      setInterval(() => {
        this.isBluetoothOpen = BleLib.isEnabled()
      }, 1000)
    },

    disconnectDevice(id) {
      const device = this.deviceList.find((item) => item.id == id)
      if (!device) return
      if (this.collectionState.active?.device_code === device.device_code) this.stopCollection('disconnect')
      this.invalidateConnection(device.device_code, true)
      // 断开后清空首页实时显示，避免残留上一次的数据
      this.realtime = emptyRealtime()
      this.gpsRealtime = null
    },

    connectDevice(id) {
      uni.showLoading({
        title: '连接中..'
      })
      const device = this.deviceList.find((item) => item.id == id)

      // 当前连接对象
      const currentBle = device && this.bles_objs[device.device_code]
      if (!currentBle) { uni.hideLoading(); return }

      if (currentBle.isConnected || currentBle.connecting) {
        uni.showToast({
          title: '当前设备已连接',
          icon: 'none'
        })
        uni.hideLoading()
        return
      }

      if (!this.isBluetoothOpen) {
        uni.showToast({
          title: '蓝牙未开启',
          icon: 'none'
        })
        uni.hideLoading()
        return
      }

      this.invalidateConnection(device.device_code)
      currentBle.connecting = true
      let epoch = currentBle.connectionEpoch
      const current = () => this.bles_objs[device.device_code] === currentBle && currentBle.connectionEpoch === epoch
      // Android BLE 首次 connectGatt 偶发失败（GATT 133 等），允许自动重试一次
      let retriesLeft = 1
      // 是否已成功连上过：区分「首连失败重试」与「已连后掉线/手动断开」——后者绝不能自动重连
      let connected = false
      const timer = currentBle.connectTimer = setTimeout(() => {
        if (!current()) return
        this.invalidateConnection(device.device_code, true)
        uni.showToast({
          title: '连接超时,请检查设备是否开启',
          icon: 'none'
        })
        uni.hideLoading()
      }, 10000)

      // autoConnect=false：点击即连这种直连场景更快更稳；true 只适合断线后台慢速重连，是首连必失败的主因
      const tryConnect = () => {
      if (!current()) return
      const attemptEpoch = epoch
      const currentAttempt = () => this.bles_objs[device.device_code] === currentBle && currentBle.connectionEpoch === attemptEpoch
      currentBle.ble.connect(device.device_code, false, (res) => {
        if (!currentAttempt()) return
        // type==0 表示连接成功 type==1
        if (res.type == 0) {
          connected = true
          currentBle.connecting = false
          this.bles_objs[device.device_code].isConnected = true
          this.collectionState.waiting = false

          currentBle.ble.scanServices(async (resSevice) => {
            if (!currentAttempt() || !currentBle.isConnected) return
            currentBle.ble.setMtu(512, () => {})

            // 获取服务数据（自定义服务固定在 data[2]：含 NOTIFY 特征 4f93ccac）
            const resSeviceData = resSevice?.data?.[2]
            if (!resSeviceData?.characteristics?.some(item => item?.properties?.NOTIFY)) {
              this.invalidateConnection(device.device_code, true)
              uni.hideLoading()
              uni.showToast({ title: '未找到鞋垫通知服务，请重新连接', icon: 'none' })
              return
            }

            // 设置服务uuid
            this.bles_objs[device.device_code].service_uuid = resSeviceData.uuid
            // 设置写特征值uuid  找到写特征值uuid
            this.bles_objs[device.device_code].write_characteristic_uuid = resSeviceData.characteristics.find((item) => item.properties['WRITE'])?.uuid || ''
            // 设置读特征值uuid 找到读特征值uuid
            this.bles_objs[device.device_code].read_characteristic_uuid = resSeviceData.characteristics.find((item) => item.properties['NOTIFY'])?.uuid || ''

            uni.showToast({
              title: '连接成功',
              icon: 'success'
            })
            uni.hideLoading()
            clearTimeout(timer)

            // 延迟2000ms
            await new Promise((resolve) => setTimeout(resolve, 2000))
            if (!currentAttempt() || !currentBle.isConnected) return
            const stream = createBleLines((line, time) => this.acceptTelemetry(device.device_code, attemptEpoch, line, time),
              () => { this.collectionState.rejected += 1 })
            currentBle.lineStream = stream
            currentBle.ble.onNotityReadBleData(currentBle.service_uuid, currentBle.read_characteristic_uuid, true, ({ data }) => {
              if (!currentAttempt() || !currentBle.isConnected || !data) return
              try { stream.push(data) } catch { this.collectionState.rejected += 1 }
            })
          })
        } else {
          // 已成功连过又收到失败回调 = 掉线/被断开：仅复位状态，绝不自动重连
          if (connected) {
            this.invalidateConnection(device.device_code)
            if (this.collectionState.active?.device_code === device.device_code) this.collectionState.waiting = true
            this.realtime = emptyRealtime()
            this.gpsRealtime = null
            uni.hideLoading()
            clearTimeout(timer)
            return
          }
          // 仅首连阶段才自动重试一次，避免把 Android 固有的偶发 GATT 失败直接抛给用户
          if (retriesLeft > 0) {
            retriesLeft--
            currentBle.retryTimer = setTimeout(() => {
              if (!currentAttempt()) return
              currentBle.connectionEpoch += 1
              epoch = currentBle.connectionEpoch
              tryConnect()
            }, 600)
            return
          }
          uni.showToast({
            title: mapper[res.type] || '连接失败',
            icon: 'none'
          })
          uni.hideLoading()
          clearTimeout(timer)
          currentBle.connecting = false
        }
      })
      }
      tryConnect()
    },

    sendMassge(data, device_code) {
      const currentBle = this.bles_objs[device_code]

      if (!currentBle.isConnected) {
        uni.showToast({
          title: '当前设备未连接',
          icon: 'none'
        })
        return
      }

      if (!currentBle.service_uuid || !currentBle.write_characteristic_uuid) {
        // uni.showToast({
        //   title: '当前设备未初始化,或者不支持写入',
        //   icon: 'none'
        // })
        return
      }

      if (!this.isBluetoothOpen) {
        uni.showToast({
          title: '蓝牙未开启',
          icon: 'none'
        })
        return
      }

      const str = this.toHex(data)
      currentBle.ble.writeStringDataToBle(currentBle.service_uuid, currentBle.write_characteristic_uuid, str.toString(), () => {})
    },

    /**
     * 获取设备列表
     */
    async getDevicesList() {
      this.deviceList = await listDevicesApi()

      const existDeviceList = Object.keys(this.bles_objs)
      // bles_objs 更新
      this.deviceList.forEach((item) => {
        if (!existDeviceList.includes(item.device_code)) {
          this.bles_objs[item.device_code] = {
            // 蓝牙对象
            ble: new BleLib(),
            // 设备id
            device_id: item.id,
            // 是否连接
            isConnected: false,
            // 服务uuid
            service_uuid: '',
            // 特征值uuid 写
            write_characteristic_uuid: '',
            // 特征值uuid 读
            read_characteristic_uuid: ''
          }
        }
      })

      Object.keys(this.bles_objs).forEach(async (device_code) => {
        const isConnected = this.bles_objs[device_code].isConnected
        // 仅当设备暴露了可写特征值时才下发频率/开关指令；
        // 当前鞋垫的自定义 service 只有 NOTIFY、无 WRITE，写不进去且设备会自行裸流数据，
        // 否则每 5s 都会刷一条「不支持写入」报错。
        if (isConnected && this.bles_objs[device_code].write_characteristic_uuid) {
          // 判断档前的发送频率 跟 开关状态
          const device = this.deviceList.find((item) => item.device_code == device_code)
          await new Promise((resolve) => setTimeout(resolve, 1000))
          this.sendMassge(device.frequency, device_code)
          await new Promise((resolve) => setTimeout(resolve, 1000))
          this.sendMassge(device.is_enabled ? '1' : '0', device_code)
        }
      })
    },
    /**
     * 添加设备
     * @param {*} deviceStr
     */
    async addDevice(deviceStr) {
      // DEVICE = Insole_1;UUID = 60bf8a57-49d5-48ff-b680-0f02149a9468
      const device = deviceStr.split(';')
      if (device.length === 2) {
        const deviceObj = {
          device_name: device[0].split('=')[1],
          device_code: device[1].split('=')[1],
          is_active: false,
          frequency: 1
        }
        await registerDeviceApi(deviceObj)
        // 设置设备列表
        await this.getDevicesList()
        uni.showToast({
          title: '添加设备成功',
          icon: 'success'
        })
      } else {
        uni.showToast({
          title: '设备信息有误',
          icon: 'none'
        })
      }
    },
    /**
     * 删除设备
     * @param {*} id
     */
    async deleteDevice(id) {
      uni.showLoading({
        title: '删除中..'
      })
      const device = this.deviceList.find((item) => item.id == id)
      if (!device) { uni.hideLoading(); return }
      if (this.collectionState.active?.device_code === device.device_code) this.stopCollection('delete')
      this.invalidateConnection(device.device_code, true)
      try {
        await deleteDeviceApiReq(id)
        delete this.bles_objs[device.device_code]
        await this.getDevicesList()
        uni.showToast({
          title: '删除设备成功',
          icon: 'success'
        })

        uni.hideLoading()
      } catch (error) {
        uni.showToast({
          title: '删除设备失败',
          icon: 'none'
        })
      }
      uni.hideLoading()
    },

    toHex(value) {
      if (typeof value === 'number') {
        // 处理数字类型
        return value.toString(16)
      } else if (typeof value === 'string') {
        // 处理字符串类型（转换每个字符为十六进制）
        let result = ''
        for (let i = 0; i < value.length; i++) {
          result += value.charCodeAt(i).toString(16).padStart(2, '0')
        }
        return result
      } else {
        // 处理其他类型（转换为字符串后按字符处理）
        return toHex(String(value))
      }
    }
  }
})

export function useBlueToothStoreWithOut() {
  return useBlueToothStore(store)
}
