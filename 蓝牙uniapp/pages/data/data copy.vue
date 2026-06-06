<template>
	<view class="container">
		<uni-notice-bar v-if="state.getWeekPlan" :speed="20" show-icon scrollable :text="state.getWeekPlan" />
		
		<!-- 动态设备图表展示 -->
		<view v-for="(device, deviceIndex) in deviceCharts" :key="device.device_code" class="device-section">
			<uni-section class="chart-section" :title="`${device.device_name} - Muscle Mass`" subTitle="" type="line" titleColor="#333"
				titleFontSize="34rpx">
				<view class="chart-container">
					<view v-if="device.optsFirst" class="chart-item">
						<qiun-data-charts :key="`${deviceIndex}-1`" type="arcbar" :opts="device.optsFirst" :chartData="device.chartDataFirst" />
					</view>
					<view v-if="device.optsSecond" class="chart-item chart-item-border">
						<qiun-data-charts :key="`${deviceIndex}-2`" type="arcbar" :opts="device.optsSecond" :chartData="device.chartDataSecond" />
					</view>
					<view v-if="device.optsThird" class="chart-item chart-item-border">
						<qiun-data-charts :key="`${deviceIndex}-3`" type="arcbar" :opts="device.optsThird" :chartData="device.chartDataThird" />
					</view>
				</view>
			</uni-section>
		</view>
		<uni-section class="chart-section" title="Bone Density" subTitle="" type="line" titleColor="#333"
			titleFontSize="34rpx">
			<view class="bar-chart-container">
				<qiun-data-charts type="column" :opts="optsBar" :chartData="chartDataBar" />
			</view>
		</uni-section>

		<uni-section class="risk-section" title="Risk" subTitle="" type="line" titleColor="#333" titleFontSize="34rpx">
			<view class="risk-container">
				<view v-for="(item, index) in state.list" :key="item.id" :class="{
            'risk-item': true,
            'risk-item-border': index != state.list.length - 1
          }">
					<text class="risk-name">{{ item.name }}</text>
					<text class="risk-value">{{ item.value }}</text>
				</view>
			</view>
		</uni-section>
	</view>
</template>

<script setup>
	import {
		onMounted,
		reactive,
		ref,
		computed
	} from 'vue'
	import {
		getRingOpts,
		getBarOpts
	} from '@/utils/ucharts'
	import {
		getUserT2T3Api,
		getUserWeekPlanApi
	} from '@/api/user'
	import {
		onShow
	} from '@dcloudio/uni-app'

	const state = reactive({
		list: [{
				name: 'Sarcopenia',
				value: '55%'
			},
			{
				name: 'Osteoporosis',
				value: '0.5%'
			},
			{
				name: `Parkinson's disease`,
				value: '0.01%'
			}
		],
		weekPlan: [],
		// 周计划
		getWeekPlan: ''
	})

	// 设备图表数据数组
	const deviceCharts = ref([])

	onShow(() => {
		getUserT2T3Api().then((res) => {
			if (Array.isArray(res) && res.length > 0) {
				// 为每个设备创建图表数据
				deviceCharts.value = res.map((device, index) => {
					const {
						device_code,
						device_name,
						last_month_T3_avg,
						last_week_T2_avg,
						this_week_T2_avg
					} = device

					// 为每个设备创建三个图表
					const optsFirst = getCommonData(
						parseFloat(this_week_T2_avg || 0)?.toFixed(6),
						'Current Week', 
						'#2fc25b'
					)
					const optsSecond = getCommonData(
						parseFloat(last_week_T2_avg || 0)?.toFixed(6),
						'Last Week', 
						'#EE6666'
					)
					const optsThird = getCommonData(
						parseFloat(last_month_T3_avg || 0)?.toFixed(6),
						'Last Month', 
						'#5c65de'
					)

					// 创建图表数据
					const chartDataFirst = {
						series: [{
							name: '正确率',
							color: '#2fc25b',
							data: parseFloat(this_week_T2_avg || 0),
							labelShow: false
						}]
					}

					const chartDataSecond = {
						series: [{
							name: '正确率',
							color: '#EE6666',
							data: parseFloat(last_week_T2_avg || 0),
							labelShow: false
						}]
					}

					const chartDataThird = {
						series: [{
							name: '正确率',
							color: '#5c65de',
							data: parseFloat(last_month_T3_avg || 0),
							labelShow: false
						}]
					}

					return {
						device_code,
						device_name,
						optsFirst,
						optsSecond,
						optsThird,
						chartDataFirst,
						chartDataSecond,
						chartDataThird
					}
				})
			} else {
				// 暂无设备时显示默认图表
				deviceCharts.value = [{
					device_code: 'default',
					device_name: 'No Device',
					optsFirst: getCommonData(0, 'Current Week', '#2fc25b'),
					optsSecond: getCommonData(0, 'Last Week', '#EE6666'),
					optsThird: getCommonData(0, 'Last Month', '#5c65de'),
					chartDataFirst: {
						series: [{
							name: '正确率',
							color: '#2fc25b',
							data: 0,
							labelShow: false
						}]
					},
					chartDataSecond: {
						series: [{
							name: '正确率',
							color: '#EE6666',
							data: 0,
							labelShow: false
						}]
					},
					chartDataThird: {
						series: [{
							name: '正确率',
							color: '#5c65de',
							data: 0,
							labelShow: false
						}]
					}
				}]
			}
		})
		
		getUserWeekPlanApi().then((res) => {
			console.log('res', res)
			const {
				monday,
				tuesday,
				wednesday,
				thursday,
				friday,
				saturday,
				sunday
			} = res.days
			state.weekPlan = [sunday, monday, tuesday, wednesday, thursday, friday, saturday]

			let result = ''
			// 判断今天是周几 (0是周日，1-6是周一到周六)
			const today = new Date().getDay()

			const target = state.weekPlan[today]

			console.log('target', target)
			console.log('today', today)

			if (target) {
				result = target.description
			}

			state.getWeekPlan = result
		})
	})

	const getCommonData = (title, subTitle, color) => {
		return getRingOpts({
			title: {
				name: title,
				fontSize: 18,
				color: color
			},
			subtitle: {
				name: subTitle,
				offsetX: 10,
				fontSize: 11,
				color: color
			}
		})
	}

	const optsBar = getBarOpts({
		legend: {
			show: true
		}
	})

	const chartDataBar = {
		categories: ['2018', '2019', '2020', '2021', '2022', '2023'],
		series: [{
				name: '目标值',
				textColor: '#FFFFFF',
				data: [35, 36, 31, 33, 13, 34],
				color: '#1890FF'
			},
			{
				name: '完成量',
				textColor: '#FFFFFF',
				data: [18, 27, 21, 24, 6, 28],
				color: '#91CB74'
			}
		]
	}
</script>

<style lang="scss" scoped>
	.device-section {
		margin-bottom: 20rpx;
	}

	.chart-section {
		margin-top: 10rpx;
	}

	.chart-container {
		display: flex;
		flex-direction: row;
		padding: 0 10rpx;
		border: 2rpx solid #F5F7FA;
		border-bottom-style: solid;
		height: 320rpx;
	}

	.chart-item {
		flex: 1;
		overflow: hidden;
		padding: 0 10rpx;
	}

	.chart-item-border {
		border-left: 2rpx solid #F5F7FA;
		border-left-style: solid;
	}

	.bar-chart-container {
		display: flex;
		padding: 0 40rpx;
	}

	.risk-section {
		margin: 10rpx 0;
	}

	.risk-container {
		display: flex;
		padding: 30rpx 40rpx;
		flex-direction: column;
	}

	.risk-item {
		flex: 1;
		padding: 30rpx 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.risk-item-border {
		border-bottom: 1rpx solid #F5F7FA;
		border-bottom-style: solid;
	}

	.risk-name {
		font-size: 28rpx;
		font-weight: 600;
	}

	.risk-value {
		font-size: 28rpx;
		font-weight: 500;
		width: 150rpx;
		text-align: left;
	}
</style>