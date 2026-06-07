import Request from '@/js_sdk/luch-request/luch-request'
import { baseURL, requestTimeout, contentType } from '@/config'
import { getToken } from '@/utils/auth'
import { useOperatorStoreWithOut } from '@/store/modules/operator'

/**
 * @description 处理code异常
 * @param {*} code
 * @param {*} msg
 */
const handleCode = (code, msg) => {
  switch (code) {
    case 4001:
      uni.showToast({
        icon: 'error',
        title: '登录身份已失效，请重新登录',
        duration: 2000
      })
      break
    case 403:
      uni.showToast({
        icon: 'error',
        title: msg,
        duration: 2000
      })
      break
    default:
      uni.showToast({
        icon: 'error',
        title: msg || `后端接口${code}异常`,
        duration: 2000
      })
      break
  }
}

/**
 * @description Request初始化
 */
const instance = new Request({
  baseURL,
  timeout: requestTimeout,
  headers: {
    'Content-Type': contentType
  },
  dataType: 'json',
  // 启用IPv4优先解析
  firstIpv4: true,
  // 禁用SSL验证（仅用于测试环境）
  sslVerify: false,
  // // 自定义params 处理函数
  // paramsSerializer: null,
  // // #ifndef MP-ALIPAY
  // responseType: 'text',
  // // #endif
  // // 注：如果局部custom与全局custom有同名属性，则后面的属性会覆盖前面的属性，相当于Object.assign(全局，局部)
  // custom: {}, // 全局自定义参数默认值
  // // #ifdef H5 || APP-PLUS || MP-ALIPAY || MP-WEIXIN
  // timeout: 60000,
  // // #endif
  // // #ifdef APP-PLUS
  // sslVerify: false,
  // // #endif
  // // #ifdef H5
  // // 跨域请求时是否携带凭证（cookies）仅H5支持（HBuilderX 2.6.15+）
  // withCredentials: false,
  // // #endif
  // // #ifdef APP-PLUS
  // firstIpv4: false // DNS解析时优先使用ipv4 仅 App-Android 支持 (HBuilderX 2.8.0+)
  // #endif
  // 局部优先级高于全局，返回当前请求的task,options。请勿在此处修改options。非必填
  // getTask: (task, options) => {
  //   // 相当于设置了请求超时时间500ms;
  //   // setTimeout(() => {
  //   //   task.abort();
  //   // }, 500);
  //   console.log(task, options);
  // }
  // 全局自定义验证器。参数为statusCode 且必存在，不用判断空情况。
  // validateStatus: (statusCode) => { // statusCode 必存在。此处示例为全局默认配置
  // 	return statusCode >= 200 && statusCode < 300
  // }
})

// 401 静默刷新并重试一次：用本地 phone+terminalCode+passcode 换新 token
async function retryWithRefresh(config) {
  if (config._retried) return Promise.reject(config)
  if (['/clinician/enable', '/clinician/login'].some((p) => config.url.includes(p))) {
    return Promise.reject(config)
  }
  const op = useOperatorStoreWithOut()
  if (!op.operator || !op.operator.passcode) return Promise.reject(config)
  await op.refreshToken()
  config._retried = true
  config.header = { ...(config.header || {}), Authorization: getToken() }
  return instance.request(config)
}

instance.interceptors.request.use(
  (config) => {
    console.log('🚀 发起请求:', {
      url: config.url,
      method: config.method,
      baseURL: config.baseURL,
      fullPath: config.baseURL + config.url,
      timeout: config.timeout,
      data: config.data
    })
    
    // token 由操作员启用/登录产生，存为 "Bearer xxx" 整串（auth.getToken）
    const token = getToken()
    // 无 token 仅放行启用/登录；其余无 token 请求静默取消（不强制登出，沿用旧策略）
    const noAuthPaths = ['/clinician/enable', '/clinician/login']
    if (token) {
      config.header['Authorization'] = token
    } else if (!noAuthPaths.some((p) => config.url.includes(p))) {
      return Promise.reject(config)
    }

    // 是否请求 出现loading
    if (config.custom.loading) {
      uni.showLoading({
        title: config.custom.loadingText || '加载中',
        mask: true
      })
    }
    return config
  },
  (config) => {
    // 可使用async await 做异步操作
    return Promise.reject(config)
  }
)

instance.interceptors.response.use(
  (response) => {
    console.log('✅ 请求成功:', {
      url: response.config.url,
      status: response.statusCode,
      data: response.data
    })
    /* 对响应成功做点什么 可使用async await 做异步操作*/
    if (response.config.custom.verification) {
      // 演示自定义参数的作用
      return response.data
    }
    const code = response.data.code || response.data.status

    if (code === 401) {
      // 静默刷新换 token 重试一次（不弹登录页、不清本地数据）
      return retryWithRefresh(response.config).catch(() => {
        uni.showToast({ icon: 'none', title: '鉴权失败，请重新解锁', duration: 2000 })
        return Promise.reject(response)
      })
    }
    if (![200].includes(code)) {
      // 服务端返回的状态码不等于200，则reject()
      // handleCode(response.data.code, response.data.msg);
      uni.showToast({
        icon: 'none',
        title: response.data.msg || '后端接口异常',
        duration: 2000
      })
      return Promise.reject(response)
    }

    return response.data.data
  },
  (error) => {
    console.error('❌ 请求失败:', {
      url: error.config?.url,
      method: error.config?.method,
      statusCode: error.statusCode,
      errMsg: error.errMsg,
      data: error.data
    })
    
    // 网络连接错误处理
    if (error.errMsg && error.errMsg.includes('request:fail')) {
      let errorMessage = '网络连接失败'
      
      if (error.errMsg.includes('timeout')) {
        errorMessage = '请求超时，请检查网络连接'
      } else if (error.errMsg.includes('abort')) {
        errorMessage = '请求被中断'
      } else if (error.errMsg.includes('Failed to connect')) {
        errorMessage = '无法连接到服务器，请检查网络或服务器状态'
      } else if (error.errMsg.includes('statusCode:-1')) {
        errorMessage = '网络连接异常，请检查网络设置'
      }
      
      uni.showToast({
        icon: 'none',
        title: errorMessage,
        duration: 3000
      })
    } else if ([401].includes(error?.data?.code) || error?.statusCode === 401) {
      return retryWithRefresh(error.config).catch(() => {
        uni.showToast({ icon: 'none', title: '鉴权失败，请重新解锁', duration: 2000 })
        return Promise.reject(error)
      })
    } else {
      // 其他错误
      uni.showToast({
        icon: 'none',
        title: error?.data?.msg || error.errMsg || '网络异常',
        duration: 2000
      })
    }
    return Promise.reject(error)
  }
)

export { instance }
