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
		state.ble.onBtOpenStateListener(function() {})

		state.ble.connect('18:8B:0E:CC:81:BD', true, function(res) {
			// type==0 表示连接成功 type==1
			if (res.type == 0) {
				state.ble.scanServices(function(resSevice) {
					state.ble.setMtu(512, function() {})

					const use_sevice = resSevice.data[2]
					const use_notify_characteristics = use_sevice.characteristics[0].uuid

					setTimeout(() => {
						state.ble.onNotityReadBleData(use_sevice.uuid,
							use_notify_characteristics,
							true,
							function() {})
					}, 1000)
				})
			}
		})
	})

	const sendMassge = (data, sericUUID = '60bf8a57-49d5-48ff-b680-0f02149a9468', writeUUID =
		'72dd0ce5-592d-40c3-b48e-2853cf9505aa') => {
		const str = toHex(data)

		state.ble.writeStringDataToBle(sericUUID, writeUUID, str.toString(), function() {})
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
