const LEGACY_OPERATOR_FIELD = ['terminal', 'Code'].join('')
const PERSISTED_SECRET_FIELD = 'passcode'

export function sanitizeOperatorProfile(profile) {
  if (
    !profile ||
    typeof profile !== 'object' ||
    (!Object.prototype.hasOwnProperty.call(profile, LEGACY_OPERATOR_FIELD) &&
      !Object.prototype.hasOwnProperty.call(profile, PERSISTED_SECRET_FIELD))
  ) {
    return profile
  }

  const sanitized = { ...profile }
  delete sanitized[LEGACY_OPERATOR_FIELD]
  delete sanitized[PERSISTED_SECRET_FIELD]
  return sanitized
}

export function buildEnableCredentials({
  hospital,
  dept,
  name,
  phone,
  passcode,
}) {
  return { hospital, dept, name, phone, passcode }
}

export function buildLoginCredentials({
  hospital,
  name,
  phone,
  passcode,
}) {
  return { hospital, name, phone, passcode }
}
