import { describe, expect, it, vi } from 'vitest'
import { createSubmissionGate } from '../utils/submissionGate'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('unlock submission gate', () => {
  it('allows only one in-flight login and reopens after completion', async () => {
    const pending = deferred()
    const stateChanges = []
    const gate = createSubmissionGate((submitting) => stateChanges.push(submitting))
    const firstLogin = vi.fn(() => pending.promise)
    const duplicateLogin = vi.fn()

    const first = gate.run(firstLogin)
    await expect(gate.run(duplicateLogin)).resolves.toEqual({ accepted: false })
    expect(firstLogin).toHaveBeenCalledOnce()
    expect(duplicateLogin).not.toHaveBeenCalled()
    expect(gate.isSubmitting()).toBe(true)

    pending.resolve('authenticated')
    await expect(first).resolves.toEqual({ accepted: true, value: 'authenticated' })
    expect(gate.isSubmitting()).toBe(false)
    expect(stateChanges).toEqual([true, false])

    await expect(gate.run(() => Promise.resolve('next')))
      .resolves.toEqual({ accepted: true, value: 'next' })
  })

  it('reopens in finally when login fails', async () => {
    const stateChanges = []
    const gate = createSubmissionGate((submitting) => stateChanges.push(submitting))

    await expect(gate.run(() => Promise.reject(new Error('network failure'))))
      .rejects.toThrow('network failure')

    expect(gate.isSubmitting()).toBe(false)
    expect(stateChanges).toEqual([true, false])
  })
})
