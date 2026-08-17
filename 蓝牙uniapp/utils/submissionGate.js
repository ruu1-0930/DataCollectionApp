export function createSubmissionGate(onStateChange = () => {}) {
  let submitting = false

  return {
    isSubmitting() {
      return submitting
    },
    async run(task) {
      if (submitting) return { accepted: false }

      submitting = true
      onStateChange(true)
      try {
        return { accepted: true, value: await task() }
      } finally {
        submitting = false
        onStateChange(false)
      }
    },
  }
}
