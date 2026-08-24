import { describe, expect, it, vi } from 'vitest'
import {
  createSubmissionGate,
  runCommittedSubmission,
} from '../utils/submissionGate'

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

describe('setup authentication navigation', () => {
  it.each([
    ['stale enable', null],
    ['invalidated unlock', false],
  ])('does not navigate for a resolved %s result', async (_name, result) => {
    const navigate = vi.fn()

    await expect(runCommittedSubmission({
      gate: createSubmissionGate(),
      submit: () => Promise.resolve(result),
      onCommitted: navigate,
    })).resolves.toEqual({ accepted: true, value: false })

    expect(navigate).not.toHaveBeenCalled()
  })

  it('gates a duplicate enable while the first enable is pending', async () => {
    const pending = deferred()
    const gate = createSubmissionGate()
    const enable = vi.fn(() => pending.promise)
    const navigate = vi.fn()

    const first = runCommittedSubmission({ gate, submit: enable, onCommitted: navigate })
    await expect(runCommittedSubmission({ gate, submit: enable, onCommitted: navigate }))
      .resolves.toEqual({ accepted: false })
    expect(enable).toHaveBeenCalledOnce()
    expect(navigate).not.toHaveBeenCalled()

    pending.resolve({ token: 'committed-token' })
    await expect(first).resolves.toEqual({ accepted: true, value: true })
    expect(navigate).toHaveBeenCalledOnce()
  })

  it('wires both setup pages to committed-result navigation', () => {
    const enableSource = readSource('../pages/setup/enable.vue')
    const unlockSource = readSource('../pages/setup/unlock.vue')

    expect(enableSource).toContain('runCommittedSubmission')
    expect(enableSource).toContain('createSubmissionGate')
    expect(enableSource).toContain(':class="{ disabled: submitting }"')
    expect(enableSource).toContain("submitting ? '启用中…' : '注册并启用'")
    expect(unlockSource).toContain('runCommittedSubmission')
  })
})

function readSource(relativePath) {
  return require('node:fs').readFileSync(
    new URL(relativePath, import.meta.url),
    'utf8',
  )
}
