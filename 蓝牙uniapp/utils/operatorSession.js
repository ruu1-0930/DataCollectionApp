import { buildLoginCredentials, sanitizeOperatorProfile } from './clinicianCredentials'

export function buildPersistentOperator(profile, clinician) {
  return {
    ...sanitizeOperatorProfile(profile),
    clinicianId: clinician.id,
  }
}

export function createOperatorSessionRuntime() {
  return {
    authEpoch: 0,
    refreshPromise: null,
  }
}

export async function authenticateOperator({ operator, passcode, loginApi }) {
  if (!operator) throw new Error('未启用，无法登录')
  if (typeof passcode !== 'string' || !passcode) {
    throw new Error('运行期口令不可用')
  }

  const response = await loginApi(buildLoginCredentials({ ...operator, passcode }))
  return {
    token: `Bearer ${response.token}`,
    operator: buildPersistentOperator(operator, response.clinician),
  }
}

export function refreshOperatorSession({ state, runtime, loginApi, setToken, setOperator }) {
  const authEpoch = runtime.authEpoch
  if (runtime.refreshPromise?.authEpoch === authEpoch) {
    return runtime.refreshPromise.promise
  }

  const promise = authenticateOperator({
    operator: state.operator,
    passcode: state.runtimePasscode,
    loginApi,
  }).then((authenticated) => {
    if (runtime.authEpoch !== authEpoch) return null

    setToken(authenticated.token)
    state.operator = authenticated.operator
    setOperator(state.operator)
    return authenticated
  })

  runtime.refreshPromise = { authEpoch, promise }
  const clearRefreshPromise = () => {
    if (runtime.refreshPromise?.promise === promise) {
      runtime.refreshPromise = null
    }
  }
  promise.then(clearRefreshPromise, clearRefreshPromise)
  return promise
}

export function resetOperatorSession({ state, runtime, clearOperator, clearToken }) {
  runtime.authEpoch += 1
  state.operator = null
  state.runtimePasscode = null
  state.unlocked = false
  clearOperator()
  clearToken()
}
