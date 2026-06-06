/**
 * 读取文件
 * @param {*} filePath
 * @param {*} encoding
 * @returns
 */
export function getFileByPath(filePath, encoding = 'base64') {
  return new Promise((resolve, reject) => {
    uni.getFileSystemManager().readFile({
      filePath, // 使用临时路径
      encoding, // 指定读取文件的编码格式
      success(res) {
        // 在这里你可以使用 res.data 进行上传或其他操作
        // console.log('读取临时文件：', res);
        resolve(res)
      },
      fail(err) {
        console.error('读取临时文件失败：', err)
        reject(err)
      }
    })
  })
}
