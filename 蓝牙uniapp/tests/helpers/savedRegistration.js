// Fixture for tests whose subject is the existing queue/transport, with the
// registration save boundary represented by a stable already-saved object.
const registrations = new Map()
export function savedRegistration(patientId = 7) {
  if (!registrations.has(patientId)) registrations.set(patientId, Object.freeze({ schema_version: 1, patient_id: patientId,
    patient_snapshot: Object.freeze({ name: '合成患者', gender: '男', age: 60, height_cm: 170, weight_kg: 65, shoe_size_eu: 40.5 }),
    test_type: 'walk_10m_usual', remarks: '' }))
  return registrations.get(patientId)
}
