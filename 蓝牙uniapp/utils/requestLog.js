function requestMetadata(config) {
  return {
    url: config?.url || '',
    method: String(config?.method || 'GET').toUpperCase(),
  }
}

export function requestLogMetadata(config) {
  return requestMetadata(config)
}

export function responseLogMetadata(response) {
  return {
    ...requestMetadata(response?.config),
    status: response?.statusCode ?? null,
  }
}

export function errorLogMetadata(error) {
  const status = error?.statusCode ?? null
  return {
    ...requestMetadata(error?.config),
    status,
    errorCategory: status ? 'http_error' : 'network_error',
  }
}

export function logRequestStart(config) {
  console.info('HTTP request', requestLogMetadata(config))
}

export function logResponse(response) {
  console.info('HTTP response', responseLogMetadata(response))
}

export function logRequestError(error) {
  console.error('HTTP request failed', errorLogMetadata(error))
}
