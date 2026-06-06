import { cloneDeep } from 'lodash'

export function resetSetupStore(context) {
  const setupSyntaxIds = ['appStore', 'chatStore', 'managerStore', 'userStore']
  if (setupSyntaxIds.includes(context.store.$id)) {
    const { $state } = context.store

    const defaultStore = cloneDeep($state)

    context.store.$reset = () => {
      context.store.$patch(defaultStore)
    }
  }
}
