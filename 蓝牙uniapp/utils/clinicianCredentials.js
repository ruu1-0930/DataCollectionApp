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
