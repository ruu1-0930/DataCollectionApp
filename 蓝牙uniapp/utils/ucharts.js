export function getRingOpts(config) {
	const baseConfig = {
		color: ['#1890FF', '#91CB74', '#FAC858', '#EE6666', '#73C0DE', '#3CA272', '#FC8452', '#9A60B4', '#ea7ccc'],
		title: {
			name: '80%',
			fontSize: 20,
			color: '#2fc25b'
		},
		legend: {
			show: false
		},
		subtitle: {
			name: '',
			fontSize: 20,
			color: '#666666'
		},
		extra: {
			arcbar: {
				type: 'circle',
				startAngle: 1.5,
				endAngle: 0.25,
				gap: 2,
				width: 10,
				backgroundColor: '#E9E9E9'
			}
		}
	}
	return {
		...baseConfig,
		...config
	}
}

// 条形图
export function getBarOpts(config) {
	const baseConfig = {
		color: ['#1890FF', '#91CB74', '#FAC858', '#EE6666', '#73C0DE', '#3CA272', '#FC8452', '#9A60B4', '#ea7ccc'],
		padding: [15, 5, 5, 5],
		enableScroll: false,
		legend: {},
		xAxis: {
			disableGrid: true
		},
		yAxis: {
			data: [{
				min: 0
			}]
		},
		extra: {
			column: {
				type: 'stack',
				width: 30,
				activeBgColor: '#000000',
				activeBgOpacity: 0.08,
				labelPosition: 'center'
			}
		}
	}
	return {
		...baseConfig,
		...config
	}
}