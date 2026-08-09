const LEGACY_OPERATOR_FIELD = ['terminal', 'Code'].join('')

export function sanitizeOperatorProfile(profile) {
  if (
    !profile ||
    typeof profile !== 'object' ||
    !Object.prototype.hasOwnProperty.call(profile, LEGACY_OPERATOR_FIELD)
  ) {
    return profile
  }

  const sanitized = { ...profile }
  delete sanitized[LEGACY_OPERATOR_FIELD]
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
