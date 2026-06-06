/**
 * 网络诊断工具
 * 用于排查网络连接问题
 */

import { baseURL } from '@/config'

/**
 * 测试网络连接
 */
export const testNetworkConnection = () => {
  return new Promise((resolve, reject) => {
    // 测试基本网络连接
    uni.request({
      url: 'https://www.baidu.com',
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        console.log('✅ 基本网络连接正常')
        resolve({ basic: true, message: '基本网络连接正常' })
      },
      fail: (err) => {
        console.error('❌ 基本网络连接失败:', err)
        reject({ basic: false, message: '基本网络连接失败', error: err })
      }
    })
  })
}

/**
 * 测试服务器连接
 */
export const testServerConnection = () => {
  return new Promise((resolve, reject) => {
    const serverUrl = baseURL.replace('http://', '').replace('https://', '')
    const [host, port] = serverUrl.split(':')
    
    console.log('🔍 测试服务器连接:', { host, port })
    
    // 尝试连接服务器
    uni.request({
      url: `${baseURL}/health`, // 假设有健康检查接口
      method: 'GET',
      timeout: 10000,
      success: (res) => {
        console.log('✅ 服务器连接正常')
        resolve({ server: true, message: '服务器连接正常', data: res.data })
      },
      fail: (err) => {
        console.error('❌ 服务器连接失败:', err)
        
        // 尝试ping测试
        testPing(host).then(pingResult => {
          resolve({ 
            server: false, 
            message: '服务器连接失败', 
            error: err,
            ping: pingResult
          })
        }).catch(pingErr => {
          resolve({ 
            server: false, 
            message: '服务器连接失败', 
            error: err,
            ping: { success: false, error: pingErr }
          })
        })
      }
    })
  })
}

/**
 * 简单的ping测试（通过请求根路径）
 */
export const testPing = (host) => {
  return new Promise((resolve) => {
    uni.request({
      url: `http://${host}`,
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        resolve({ success: true, message: '主机可达' })
      },
      fail: (err) => {
        resolve({ success: false, message: '主机不可达', error: err })
      }
    })
  })
}

/**
 * 完整的网络诊断
 */
export const runNetworkDiagnostic = async () => {
  console.log('🔍 开始网络诊断...')
  
  const results = {
    timestamp: new Date().toISOString(),
    basic: null,
    server: null,
    recommendations: []
  }
  
  try {
    // 测试基本网络
    results.basic = await testNetworkConnection()
  } catch (error) {
    results.basic = error
    results.recommendations.push('检查设备网络连接')
    results.recommendations.push('检查WiFi或移动数据是否正常')
  }
  
  try {
    // 测试服务器连接
    results.server = await testServerConnection()
  } catch (error) {
    results.server = error
  }
  
  // 生成建议
  if (results.server && !results.server.server) {
    if (results.server.ping && !results.server.ping.success) {
      results.recommendations.push('服务器主机不可达，请检查服务器是否运行')
      results.recommendations.push('检查防火墙设置是否阻止了连接')
    } else {
      results.recommendations.push('服务器主机可达但服务不可用')
      results.recommendations.push('检查服务器 80/443 端口是否开放（请求经 nginx 反代到后端）')
      results.recommendations.push('检查服务器应用是否正常运行')
    }
  }
  
  console.log('📊 网络诊断结果:', results)
  return results
}

/**
 * 显示网络诊断结果
 */
export const showNetworkDiagnostic = async () => {
  uni.showLoading({ title: '网络诊断中...' })
  
  try {
    const results = await runNetworkDiagnostic()
    uni.hideLoading()
    
    let message = '网络诊断完成\n\n'
    
    if (results.basic && results.basic.basic) {
      message += '✅ 基本网络: 正常\n'
    } else {
      message += '❌ 基本网络: 异常\n'
    }
    
    if (results.server && results.server.server) {
      message += '✅ 服务器连接: 正常\n'
    } else {
      message += '❌ 服务器连接: 异常\n'
    }
    
    if (results.recommendations.length > 0) {
      message += '\n建议:\n'
      results.recommendations.forEach((rec, index) => {
        message += `${index + 1}. ${rec}\n`
      })
    }
    
    uni.showModal({
      title: '网络诊断结果',
      content: message,
      showCancel: false
    })
    
  } catch (error) {
    uni.hideLoading()
    uni.showToast({
      title: '诊断失败',
      icon: 'error'
    })
  }
}
