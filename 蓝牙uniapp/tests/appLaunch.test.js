import { describe, expect, it } from 'vitest'
import { resolveLaunchRoute } from '../utils/appLaunch'

describe('application launch authorization gate', () => {
  it('requires remote unlock after restart even when a persisted token exists', () => {
    expect(resolveLaunchRoute({
      enabled: true,
      unlocked: false,
      hasPatient: true,
      hasToken: true,
    })).toBe('/pages/setup/unlock')
  })

  it('routes only an unlocked runtime session into patient workflow', () => {
    expect(resolveLaunchRoute({ enabled: false, unlocked: false, hasPatient: false }))
      .toBe('/pages/setup/enable')
    expect(resolveLaunchRoute({ enabled: true, unlocked: true, hasPatient: false }))
      .toBe('/pages/patient/select')
    expect(resolveLaunchRoute({ enabled: true, unlocked: true, hasPatient: true }))
      .toBe(null)
  })
})
