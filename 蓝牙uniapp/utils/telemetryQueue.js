const copy = value => JSON.parse(JSON.stringify(value))
// One lane only. Persistence, ownership, create and stop belong to the coordinator.
export function createTelemetryOutbox({ capacity = 5000, events = [] } = {}) {
  let pending = copy(events)
  return {
    enqueue(event) {
      if (pending.length >= capacity) throw Error('capacity')
      pending.push(copy(event))
    },
    peekBatch() {
      const batch = [], stream = pending[0]?.stream
      for (const event of pending) {
        if (batch.length === 50 || event.stream !== stream) break
        if (JSON.stringify({ events: [...batch, event] }).length * 3 > 128 * 1024) break
        batch.push(copy(event))
      }
      return batch
    },
    ack(ids) { const accepted = new Set(ids); pending = pending.filter(e => !accepted.has(e.event_id)) },
    snapshot() { return copy(pending) },
  }
}
