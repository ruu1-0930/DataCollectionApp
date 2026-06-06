/**
 * 获取系统信息
 * @returns
 */
export function getSystemInfo() {
  return uni.getSystemInfoSync()
}

// rpx转px
export function rpxToPx(rpx) {
  return uni.upx2px(rpx)
}

// px转rpx
export function pxToRpx(px) {
  //计算比例
  let scale = uni.upx2px(100) / 100
  return px / scale
}
