export * from './auth'
export * from './request'
export * from './processFile'
export * from './str'
export * from './system'

function pageTo(url) {

  if (url.includes('/login')) {
    uni.redirectTo({
      url: url
    })
    return
  }

  try {
    // 振动
    uni.vibrateShort()
    uni.navigateTo({
      url: url,
      animationType: 'pop-in',
      animationDuration: 100
    })
  } catch (error) {
    console.error('Navigation error:', error)
    // 这里可以添加错误处理逻辑，例如显示一个错误提示给用户
  }
}

export { pageTo }
