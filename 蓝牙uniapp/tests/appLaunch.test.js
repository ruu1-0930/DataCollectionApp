import { describe, expect, it, vi } from 'vitest'
import { prepareAppLaunch, resolveLaunchRoute } from '../utils/appLaunch'

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

  it.each([
    [false, false, '/pages/setup/enable'],
    [true, true, '/pages/setup/unlock'],
  ])('clears the persisted token before routing a locked runtime session', (
    enabled,
    hasPatient,
    expectedRoute,
  ) => {
    const events = []
    const clearToken = vi.fn(() => events.push('token-cleared'))

    const route = prepareAppLaunch({
      enabled,
      unlocked: false,
      hasPatient,
      clearToken,
    })
    events.push(`route:${route}`)

    expect(events).toEqual(['token-cleared', `route:${expectedRoute}`])
    expect(clearToken).toHaveBeenCalledOnce()
  })

  it('does not clear the current token for an unlocked runtime session', () => {
    const clearToken = vi.fn()

    expect(prepareAppLaunch({
      enabled: true,
      unlocked: true,
      hasPatient: false,
      clearToken,
    })).toBe('/pages/patient/select')
    expect(clearToken).not.toHaveBeenCalled()
  })
})
