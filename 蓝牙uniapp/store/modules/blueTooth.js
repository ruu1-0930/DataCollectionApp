import { defineStore } from 'pinia'
import { store } from '@/store'
import { listDevicesApi, registerDeviceApi, deleteDeviceApi as deleteDeviceApiReq, uploadRawDataApi } from '@/api'
import { buildRawDataPayload } from '@/utils/apiShape'
import { usePatientStoreWithOut } from '@/store/modules/patient'
import { BleLib } from '@/uni_modules/android-ble'

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
      isScanning: false
    }
  },
  getters: {},
  actions: {
    // 实时同步系统蓝牙开关状态（initBle 的监听只在“切换”时触发，启动前已开启的情况要主动查一次）
    syncBluetoothState() {
      // #ifdef APP-PLUS
      try {
        this.isBluetoothOpen = this.globalBle.isEnabled()
      } catch (e) {
        console.warn('读取蓝牙状态失败', e)
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
            (err) => {
              console.warn('申请蓝牙权限失败', err)
              resolve(false)
            }
          )
        } catch (e) {
          console.warn('requestPermissions 异常', e)
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
          if (res?.type != null) console.log('扫描回调非结果帧', res.type, res.message)
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
        console.log('监听到蓝牙状态改变', res.data ? '蓝牙开启' : '蓝牙关闭')
        this.isBluetoothOpen = res.data ? true : false

        if (!res.data) {
          // 需要吧所有设备连接状态设置为false
          Object.keys(this.bles_objs).forEach((device_code) => {
            this.bles_objs[device_code].isConnected = false
            this.bles_objs[device_code].ble.close()
          })
        }
      })
    },

    // 检测蓝牙是否开启
    checkBluetooth() {
      setInterval(() => {
        this.isBluetoothOpen = BleLib.isEnabled()
        console.log('当前蓝牙状态', this.isBluetoothOpen)
      }, 1000)
    },

    disconnectDevice(id) {
      const device = this.deviceList.find((item) => item.id == id)
      this.bles_objs[device.device_code].isConnected = false
      this.bles_objs[device.device_code].ble.close()
      console.log(`${device.device_code} 断开连接`)
    },

    connectDevice(id) {
      uni.showLoading({
        title: '连接中..'
      })
      const device = this.deviceList.find((item) => item.id == id)

      // 当前连接对象
      const currentBle = this.bles_objs[device.device_code]

      if (currentBle.isConnected) {
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

   const timer = setTimeout(() => {
        uni.showToast({
          title: '连接超时,请检查设备是否开启',
          icon: 'none'
        })
        uni.hideLoading()
        clearTimeout(timer)
        return
      }, 10000)

      currentBle.ble.connect(device.device_code, true, (res) => {
        console.log(`${device.device_code} 连接结果`, res)
        // type==0 表示连接成功 type==1
        if (res.type == 0) {
          this.bles_objs[device.device_code].isConnected = true

          currentBle.ble.scanServices(async (resSevice) => {
            currentBle.ble.setMtu(512, (res) => {
              console.log('setMtu', res)
            })

            console.log('服务数据', resSevice)

            // 获取服务数据
            const resSeviceData = resSevice.data[2]

            console.log('resSeviceData', resSeviceData)
            
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

            currentBle.ble.onNotityReadBleData(currentBle.service_uuid, currentBle.read_characteristic_uuid, true, ({ data }) => {
              const value = new Uint8Array(data)
              // 将 ArrayBuffer 转换为字符串
              const stringValue = Array.from(value)
                .map((byte) => String.fromCharCode(byte))
                .join('')

              // 替换掉\n
              const dataArray = stringValue.split(',').map((item) => item.replace('\n', ''))
              // console.log('拿到通知数据', dataArray)

              // 效果验证 长度40个字符串
              if (dataArray.length != 38) {
                console.log('数据长度不正确', dataArray.length)
                return
              }

              const apiData = {
                // 左脚压力值 0-9
                lp1: parseFloat(dataArray[0]),
                lp2: parseFloat(dataArray[1]),
                lp3: parseFloat(dataArray[2]),
                lp4: parseFloat(dataArray[3]),
                lp5: parseFloat(dataArray[4]),
                lp6: parseFloat(dataArray[5]),
                lp7: parseFloat(dataArray[6]),
                lp8: parseFloat(dataArray[7]),
                lp9: parseFloat(dataArray[8]),

                // 左脚
                ax: parseFloat(dataArray[9]),
                ay: parseFloat(dataArray[10]),
                az: parseFloat(dataArray[11]),
                gx: parseFloat(dataArray[12]),
                gy: parseFloat(dataArray[13]),
                gz: parseFloat(dataArray[14]),

                // 左脚步长
                left_step_size: parseFloat(dataArray[15]),
                // 左脚步速
                left_speed: parseFloat(dataArray[16]),
                // 左脚单支撑
                left_single_sp_time: parseFloat(dataArray[17]),
                // 左脚双支撑
                left_double_sp_time: parseFloat(dataArray[18]),

                // 右脚压力值 20-28
                rp1: parseFloat(dataArray[19]),
                rp2: parseFloat(dataArray[20]),
                rp3: parseFloat(dataArray[21]),
                rp4: parseFloat(dataArray[22]),
                rp5: parseFloat(dataArray[23]),
                rp6: parseFloat(dataArray[24]),
                rp7: parseFloat(dataArray[25]),
                rp8: parseFloat(dataArray[26]),
                rp9: parseFloat(dataArray[27]),

                // 右脚
                right_ax: parseFloat(dataArray[28]),
                right_ay: parseFloat(dataArray[29]),
                right_az: parseFloat(dataArray[30]),
                right_gx: parseFloat(dataArray[31]),
                right_gy: parseFloat(dataArray[32]),
                right_gz: parseFloat(dataArray[33]),

                // 右脚步长
                right_step_size: parseFloat(dataArray[34]),
                // 右脚步速
                right_speed: parseFloat(dataArray[35]),
                // 右脚单支撑
                right_single_sp_time: parseFloat(dataArray[36]),
                // 右脚双支撑
                right_double_sp_time: parseFloat(dataArray[37])
              }

              // console.log('apiData', apiData)
              const ps = usePatientStoreWithOut()
              const patientId = ps.currentId
              if (!patientId) {
                // 无当前患者：禁止上传（避免数据无法归属）
                console.warn('未选择患者，已跳过本帧上传')
                return
              }
              uploadRawDataApi(device.device_code, buildRawDataPayload(patientId, apiData))
            })
          })
        } else {
          uni.showToast({
            title: mapper[res.type] || '连接失败',
            icon: 'none'
          })
          uni.hideLoading()
          clearTimeout(timer)
        }
      })
    },

    sendMassge(data, device_code) {
      const currentBle = this.bles_objs[device_code]

      console.log(`服务uuid：${currentBle.service_uuid}  写uuid:${currentBle.write_characteristic_uuid}  通知：${currentBle.read_characteristic_uuid}`)

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
        console.error('当前设备未初始化,或者不支持写入')
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
      console.log(`${device_code} 发送数据`, data, str)

      currentBle.ble.writeStringDataToBle(currentBle.service_uuid, currentBle.write_characteristic_uuid, str.toString(), (res) => {
        console.log(`${device_code} 发送数据结果`, res)
      })
    },

    /**
     * 获取设备列表
     */
    async getDevicesList() {
      this.deviceList = await listDevicesApi()
      console.log('设备列表', this.deviceList)

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
        if (isConnected) {
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
      try {
        await deleteDeviceApiReq(id)
        const device = this.deviceList.find((item) => item.id == id)
        this.bles_objs[device.device_code].ble.close()
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
