import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearToken } from '../utils/auth'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('token storage', () => {
  it('removes the persisted bearer token', () => {
    const removeStorageSync = vi.fn()
    vi.stubGlobal('uni', { removeStorageSync })

    clearToken()

    expect(removeStorageSync).toHaveBeenCalledOnce()
    expect(removeStorageSync).toHaveBeenCalledWith('__token__')
  })
})
