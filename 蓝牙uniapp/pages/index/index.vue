<template>
	<view>
		<input type="text" v-model="state.send" style="background-color: red;height: 50px;" />
		<button @click="send">发送</button>
	</view>
</template>

<script setup>
	import {
		reactive
	} from 'vue'
	import {
		onLoad
	} from '@dcloudio/uni-app'
	import {
		BleLib
	} from '@/uni_modules/android-ble'

	const state = reactive({
		ble: new BleLib(),
		send: ''
	})

	onLoad(() => {
		var open = state.ble.isEnabled() // true 为蓝牙开启 false 为关闭
		console.log(open)

		state.ble.onBtOpenStateListener(function(res) {
			console.log(res)
			if (res.data) {
				console.log('蓝牙开启')
			} else {
				console.log('蓝牙关闭')
			}
		})

		state.ble.connect('18:8B:0E:CC:81:BD', true, function(res) {
			console.log('res', res)
			// type==0 表示连接成功 type==1
			if (res.type == 0) {
				var isconnect = state.ble.isConnected()
				console.log('isconnect', isconnect)

				var device = state.ble.getConnectMac() // 已经连接返回mac 地址 未连接返回“”
				console.log('device', device)

				state.ble.scanServices(function(resSevice) {
					state.ble.setMtu(512, function(res) {
						console.log('setMtu', res)
					})

					const use_sevice = resSevice.data[2]
					const use_write_characteristics = use_sevice.characteristics[1].uuid
					const use_notify_characteristics = use_sevice.characteristics[0].uuid

					console.log(
						`服务uuid：${use_sevice.uuid}  写uuid:${use_write_characteristics}  通知：${use_notify_characteristics}`
					);

					// state.ble.writeDataToBle(use_sevice.uuid, use_write_characteristics,
					// 	'1',
					// 	function(res) {
					// 		console.log("写", res)
					// 	})
					setTimeout(() => {
						state.ble.onNotityReadBleData(use_sevice.uuid,
							use_notify_characteristics,
							true,
							function(res) {
								console.log('拿到通知数据', res)
							})
					}, 1000)
					// sendMassge('10HZ', use_sevice.uuid, use_write_characteristics)
				})
			}
		})
	})

	const sendMassge = (data, sericUUID = '60bf8a57-49d5-48ff-b680-0f02149a9468', writeUUID =
		'72dd0ce5-592d-40c3-b48e-2853cf9505aa') => {
		const str = toHex(data)
		console.log(str);

		state.ble.writeStringDataToBle(sericUUID, writeUUID, str.toString(), function(res) {
			console.log("发送回调", res)
		})
	}

	const send = () => {
		sendMassge(state.send)
	}

	function toHex(value) {
		if (typeof value === 'number') {
			// 处理数字类型
			return value.toString(16);
		} else if (typeof value === 'string') {
			// 处理字符串类型（转换每个字符为十六进制）
			let result = '';
			for (let i = 0; i < value.length; i++) {
				result += value.charCodeAt(i).toString(16).padStart(2, '0');
			}
			return result;
		} else {
			// 处理其他类型（转换为字符串后按字符处理）
			return toHex(String(value));
		}
	}
</script>

<style scoped lang="scss"></style>