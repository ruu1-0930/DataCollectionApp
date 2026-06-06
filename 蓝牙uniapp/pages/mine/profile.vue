<template>
	<view class="profile-container">
		<form @submit.prevent="submitForm">
			<view class="form-group">
				<text>用户头像</text>
				<img class="user-avatar-img" :src="`${baseURL}/${user.avatar}`" alt="" srcset=""
					@tap="uploadAvatar" />
			</view>
			<view class="form-group">
				<text>用户名称</text>
				<view @click="clickDisabled('name')" class="disabled-field">{{ user.name }}</view>
				<!-- <input @click="clickName" type="text" v-model="user.name" disabled placeholder="请输入用户名称" /> -->
			</view>
			<view class="form-group">
				<text>性别</text>
				<picker class="picker-container" mode="selector" :range="genders" @change="onGenderChange">
					<view v-if="user.gender" class="picker">
						{{ user.gender }}
					</view>
					<view v-else class="picker picker-placeholder"> 请选择性别 </view>
				</picker>
			</view>
			<view class="form-group">
				<text>年龄</text>
				<input type="number" v-model="user.age" placeholder="请输入年龄" />
			</view>
			<view class="form-group">
				<text>地址</text>
				<input type="text" v-model="user.address" placeholder="请输入地址" />
			</view>
			<view class="form-group">
				<text>电话</text>
				<!-- <input type="text" disabled v-model="user.phone" placeholder="请输入电话" /> -->
				<view @click="clickDisabled('phone')" class="disabled-field">{{ user.phone }}</view>
			</view>
			<view class="form-group">
				<text>邮箱</text>
				<input type="email" v-model="user.email" placeholder="请输入邮箱" />
			</view>
			<view class="form-group">
				<text>紧急邮箱</text>
				<input type="email" v-model="user.emergency_email" placeholder="请输入紧急邮箱" />
			</view>
			<view class="form-group">
				<text>紧急电话</text>
				<input type="number" v-model="user.emergency_phone" placeholder="请输入紧急电话" />
			</view>
			<button type="submit" @tap="updateUserInfo" class="submit-button">修改</button>
		</form>
	</view>
</template>

<script setup>
	import {
		onMounted,
		ref
	} from 'vue'
	import {
		useUserStoreWithOut
	} from '@/store'
	import {
		baseURL
	} from '@/config'
	import {
		userAvatarUploadApi
	} from '@/api'
	const userStore = useUserStoreWithOut()

	const user = ref({
		// 用户名称
		name: '',
		// 性别
		gender: '',
		// 年龄
		age: '',
		// 地址
		address: '',
		// 电话
		phone: '',
		// 邮箱
		email: '',
		// 紧急邮箱
		emergency_email: '',
		// 紧急电话
		emergency_phone: '',
		// 头像
		avatar: ''
	})

	const genders = ['男', '女', '其他']

	onMounted(() => {
		user.value = userStore.user
		delete user.value.token
	})

	function submitForm() {
		// Handle form submission
		console.log('User data:', user.value)
	}

	const onGenderChange = (event) => {
		user.value.gender = genders[event.detail.value]
	}

	function clickDisabled(key) {
		if (key === 'name') {
			uni.showToast({
				title: '暂不支持修改名称',
				icon: 'none'
			})
		}
		if (key === 'phone') {
			uni.showToast({
				title: '暂不支持修改电话',
				icon: 'none'
			})
		}
	}

	function uploadAvatar() {
		// 实现逻辑
		uni.chooseImage({
			count: 1,
			sizeType: ['compressed'],
			sourceType: ['album'],
			success: (res) => {
				console.log(res)
				uni.uploadFile({
					url: baseURL + '/upload_avatar', //仅为示例，非真实的接口地址
					filePath: res.tempFilePaths[0],
					name: 'file',
					success: (uploadFileRes) => {
						user.value.avatar = JSON.parse(uploadFileRes.data).data.avatar_url
					}
				})
			}
		})
	}

	async function updateUserInfo() {
		// 判断必填
		if (!user.value.name) {
			uni.showToast({
				title: '请输入用户名称',
				icon: 'none'
			})
			return
		}
		if (!user.value.gender) {
			uni.showToast({
				title: '请选择性别',
				icon: 'none'
			})
			return
		}
		if (!user.value.age) {
			uni.showToast({
				title: '请输入年龄',
				icon: 'none'
			})
			return
		}
		if (!user.value.address) {
			uni.showToast({
				title: '请输入地址',
				icon: 'none'
			})
			return
		}

		if (!user.value.phone) {
			uni.showToast({
				title: '请输入电话',
				icon: 'none'
			})
			return
		}

		if (!user.value.email) {
			uni.showToast({
				title: '请输入邮箱',
				icon: 'none'
			})
			return
		}
		// 正则判断邮箱
		if (!/^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$/.test(user.value.email)) {
			uni.showToast({
				title: '请输入正确的邮箱',
				icon: 'none'
			})
			return
		}

		if (!user.value.emergency_email) {
			uni.showToast({
				title: '请输入紧急邮箱',
				icon: 'none'
			})
			return
		}

		if (!user.value.emergency_phone) {
			uni.showToast({
				title: '请输入紧急电话',
				icon: 'none'
			})
			return
		}

		if (!user.value.avatar) {
			uni.showToast({
				title: '请上传头像',
				icon: 'none'
			})
			return
		}

		// 修改用户信息
		await userStore.updateUserInfo(user.value)

		uni.showToast({
			title: '修改成功',
			icon: 'success'
		})
		setTimeout(() => {
			uni.navigateBack()
		}, 300)
	}
</script>

<style lang="scss" scoped>
	.profile-container {
		padding: 20rpx;
		background-color: #f9f9f9;
	}

	input {
		height: 74rpx;
		border-radius: 10rpx;
		padding: 0 20rpx;

		::placeholder {
			color: #999;
		}
	}

	.title {
		font-size: 24px;
		font-weight: bold;
		margin-bottom: 20px;
	}

	.form-group {
		display: flex;
		align-items: center;
		padding: 20rpx;
		background-color: #fff;
		border-bottom: 2rpx solid #f5f6f7;

		&:last-child {
			border-bottom: none !important;
		}
	}

	.form-group text {
		display: block;
		margin-bottom: 5px;
		font-size: 16px;
		width: 160rpx;
	}

	.form-group {

		input,
		piker {
			flex: 1;
			margin-top: 0;
		}
	}

	input,
	.picker {
		width: 100%;
		padding: 8px;
		// border: 1px solid #ccc;
		border-radius: 8rpx;
		font-size: 26rpx;
	}

	.user-avatar-img {
		height: 120rpx;
		width: 120rpx;
		margin-left: 10rpx;
	}

	.disabled-field {
		line-height: 74rpx;
	}

	.picker-container {
		flex: 1;
	}

	.picker-placeholder {
		color: #999;
	}

	.submit-button {
		width: 100%;
		background-color: #007aff;
		color: white;
		border: none;
		border-radius: 40rpx;
		cursor: pointer;
		margin-top: 60rpx;
	}
</style>