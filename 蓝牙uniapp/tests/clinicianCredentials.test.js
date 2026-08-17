import { describe, expect, it } from 'vitest'
import * as clinicianCredentials from '../utils/clinicianCredentials'
import {
  buildEnableCredentials,
  buildLoginCredentials,
} from '../utils/clinicianCredentials'

const operator = {
  hospital: '协和医院',
  dept: '骨科',
  name: '王医生',
  phone: '13800000000',
  passcode: '1234',
  terminalCode: 'must-not-leak',
}

describe('clinician credential payloads', () => {
  it('removes persisted credentials and the exact legacy terminal identity from an operator profile', () => {
    expect(clinicianCredentials.sanitizeOperatorProfile(operator)).toEqual({
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
    })
  })

  it('builds enable profile and credentials without terminal identity', () => {
    expect(buildEnableCredentials(operator)).toEqual({
      hospital: '协和医院',
      dept: '骨科',
      name: '王医生',
      phone: '13800000000',
      passcode: '1234',
    })
  })

  it('builds refresh login credentials without dept or terminal identity', () => {
    expect(buildLoginCredentials(operator)).toEqual({
      hospital: '协和医院',
      name: '王医生',
      phone: '13800000000',
      passcode: '1234',
    })
  })
})
