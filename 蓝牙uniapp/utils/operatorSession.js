import { buildLoginCredentials, sanitizeOperatorProfile } from './clinicianCredentials'

export function buildPersistentOperator(profile, clinician) {
  return {
    ...sanitizeOperatorProfile(profile),
    clinicianId: clinician.id,
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
