const UserKey = '__user__'

export function getUser() {
  try {
    const user = uni.getStorageSync(UserKey)
    if (user) {
      return user
    }
  } catch (error) {}
  return {}
}

export function setUser(User) {
  return uni.setStorageSync(UserKey, User)
}

export function removeUser() {
  return uni.removeStorageSync(UserKey)
}

export function setToken(token) {
  return uni.setStorageSync('__token__', token)
}
export function getToken() {
  return uni.getStorageSync('__token__')
}