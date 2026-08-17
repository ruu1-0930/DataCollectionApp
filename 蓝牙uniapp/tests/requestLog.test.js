import { describe, expect, it, vi } from 'vitest'
import {
  errorLogMetadata,
  requestLogMetadata,
  responseLogMetadata,
} from '../utils/requestLog'

describe('request logging privacy boundary', () => {
  it('logs only request URL and method, never credential, patient, or sensor payload', () => {
    expect(requestLogMetadata({
      url: '/devices/INSOLE-001/raw_data',
      method: 'post',
      data: { passcode: 'secret', patient_id: 7, lp1: 902, ax: 1.2 },
      header: { Authorization: 'Bearer token-value' },
    })).toEqual({
      url: '/devices/INSOLE-001/raw_data',
      method: 'POST',
    })
  })

  it('logs only response status and does not expose response body or bearer token', () => {
    expect(responseLogMetadata({
      statusCode: 200,
      config: { url: '/patients/7', method: 'get' },
      data: { token: 'Bearer token-value', patient: { phone: '13800000000' } },
    })).toEqual({ url: '/patients/7', method: 'GET', status: 200 })
  })

  it('reduces request failures to a non-sensitive error category', () => {
    expect(errorLogMetadata({
      statusCode: 401,
      errMsg: 'Bearer token-value patient_id=7 lp1=902',
      data: { passcode: 'secret' },
      config: { url: '/clinician/login', method: 'post' },
    })).toEqual({
      url: '/clinician/login',
      method: 'POST',
      status: 401,
      errorCategory: 'http_error',
    })
  })

  it('does not let request.js directly log request, response, or error payload fields', () => {
    const source = require('node:fs').readFileSync(
      new URL('../utils/request.js', import.meta.url),
      'utf8',
    )
    expect(source).toContain("from '@/utils/requestLog'")
    expect(source).not.toMatch(
      /console\.(?:log|info|error)\([\s\S]{0,500}?(?:config\.data|response\.data|error\.data)/,
    )
  })
})
