export function collectionStopReceipt(id, body) {
  if (body.schema_version === 2) {
    return { capture_id: id, verification: { record_id: id, record_version: 'f'.repeat(64),
      observed_at: body.mobile_stopped_at, expected_counts: body.final_counts, received_counts: body.final_counts,
      upload_state: 'verified', quality_observations: [] } }
  }
  return { capture_id: id }
}
