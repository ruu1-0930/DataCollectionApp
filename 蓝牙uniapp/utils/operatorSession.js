import {
  buildEnableCredentials,
  buildLoginCredentials,
  sanitizeOperatorProfile,
} from './clinicianCredentials'

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

function beginExplicitAuthentication(runtime) {
  runtime.authEpoch += 1
  return runtime.authEpoch
}

export function enableOperatorSession({
  state,
  runtime,
  credentials,
  enableApi,
  setToken,
  setOperator,
}) {
  const authEpoch = beginExplicitAuthentication(runtime)
  const { hospital, dept, name, phone, passcode } = credentials

  return enableApi(buildEnableCredentials(credentials)).then((response) => {
    if (runtime.authEpoch !== authEpoch) return null

    setToken(`Bearer ${response.token}`)
    state.operator = buildPersistentOperator({
      hospital,
      dept,
      name,
      phone,
      enabled: true,
    }, response.clinician)
    setOperator(state.operator)
    state.runtimePasscode = passcode
    state.unlocked = true
    return response
  })
}

export function unlockOperatorSession({
  state,
  runtime,
  passcode,
  loginApi,
  setToken,
  setOperator,
}) {
  const authEpoch = beginExplicitAuthentication(runtime)

  return authenticateOperator({
    operator: state.operator,
    passcode,
    loginApi,
  }).then((authenticated) => {
    if (runtime.authEpoch !== authEpoch) return false

    setToken(authenticated.token)
    state.operator = authenticated.operator
    setOperator(state.operator)
    state.runtimePasscode = passcode
    state.unlocked = true
    return true
  })
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
