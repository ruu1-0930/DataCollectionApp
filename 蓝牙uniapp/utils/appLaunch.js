export function resolveLaunchRoute({ enabled, unlocked, hasPatient }) {
  if (!enabled) return '/pages/setup/enable'
  if (!unlocked) return '/pages/setup/unlock'
  if (!hasPatient) return '/pages/patient/select'
  return null
}

export function prepareAppLaunch({ enabled, unlocked, hasPatient, clearToken }) {
  if (!unlocked) clearToken()
  return resolveLaunchRoute({ enabled, unlocked, hasPatient })
}
