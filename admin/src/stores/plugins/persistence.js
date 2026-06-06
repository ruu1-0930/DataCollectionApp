import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'

/**
 * 使用持久化插件
 * @param {*} store
 */
export function setupPersistedStatePlugin(store) {
  store.use(piniaPluginPersistedstate)
}
