<template>
	<view>
		<uni-popup ref="popup" type="center" :maskClick="false">
			<view class="alert-view">
				<view class="msg">{{msg}}</view>
				<scroll-view scroll-y="true" style="max-height:750rpx;width:100%;">
					<view class="contt" v-if="content" v-html="content"></view>
				</scroll-view> 
				<button class="cancel" v-if="showCancel" @click="close('cancel')">{{cancelText}}</button>
				<button class="confirm" :class="{only:!showCancel}" @click="close('confirm')">{{confirmText}}</button>
			</view>
		</uni-popup>
	</view>
</template>
<script> 
	export default {
		name:"tooltip-box",
		data() {
			return {
				showCancel: true,
				cancelText: "取消",
				confirmText: "确定",
				msg: '', //标题
				content: '', //内容
				tmpFuncSuccess: '',
				tmpFuncCancel: ''
			}
		},
		methods: {
			open({
				msg,//提示标题
				showCancel = true,//是否显示取消按钮
				confirm,//确认按钮方法
				cancel,//取消按钮方法
				cancelText = "取消",//左边按钮文字
				confirmText = '确定',//右边按钮文字
				content = ''//信息内容
			}) {
				this.msg = msg
				this.content = content
				this.showCancel = showCancel
				this.cancelText = cancelText
				this.confirmText = confirmText
				this.$refs.popup.open()
				if (confirm) {
					this.tmpFuncSuccess = confirm
				}else{
					this.tmpFuncSuccess = '';
				}
				if (cancel) {
					this.tmpFuncCancel = cancel
				}else{
					this.tmpFuncCancel = '';
				}
			},
			close(type) {
				this.$refs.popup.close()
				setTimeout(() => {
					if (type == "confirm") {
						let tmpFuncSuccess = this.tmpFuncSuccess;
						if (tmpFuncSuccess){
							tmpFuncSuccess(type)
						}
					} else if (type == "cancel") {
						let tmpFuncCancel = this.tmpFuncCancel; 
						if (tmpFuncCancel){
							tmpFuncCancel(type)
						}
					}
					//取消和确定的方法都要删除
					this.tmpFuncCancel = '';
					this.tmpFuncSuccess = '';
				}, 300)
			}
		}
	}
</script>
<style>
	.cancel,
	.confirm{
		border:0 !important;
	}
	.cancel::after,
	.confirm::after{
		border:0 !important;
	}
</style>
<style scoped>
	.alert-view {
		width: 650rpx;
		min-height: 230rpx;
		margin-top:50rpx;
		box-sizing: border-box;
		padding: 40rpx 50rpx;
		border-radius: 20rpx;
		background-color: #FFFFFF;
	}

	.msg {
		width: 100%;
		text-align: center;
		color: #00133D; 
		font-size: 40rpx;
		font-weight:bold;
	}

	.contt {
		width: 100%;
		margin-top: 54rpx;
		margin-bottom: 54rpx;
		text-align: center;
		color: #95A0B8;
		font-size: 32rpx;  
	}
	.cancel,
	.confirm {
		height: 90rpx;
		width: 250rpx;
		margin: 40rpx 0 0 0;
		display: inline-flex;
		justify-content: center;
		align-items: center;
		border-radius: 20rpx; 
		padding: 0;
		border:0;
	}

	.cancel {
		margin-right: 50rpx;
		color: #000000 !important;
		background: #F0F0F0 !important;
	}

	.confirm {
		background: #0050FF !important;
		color: #FDFDFD !important;
	}

	.confirm.only {
		width: 500rpx;
		display: flex !important;
		margin: 40rpx auto 0 auto;
		font-size: 40rpx;
	}
</style>
