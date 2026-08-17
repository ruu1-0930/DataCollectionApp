import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { extname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const FIRST_PARTY_PATHS = ['api', 'components', 'pages', 'store', 'utils']
const ROOT_FILES = ['App.vue', 'main.js']
const ALLOWED_CONSOLE_FILE = join(ROOT, 'utils', 'requestLog.js')

function runtimeFiles(path) {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const target = join(path, entry.name)
    if (entry.isDirectory()) return runtimeFiles(target)
    return ['.js', '.vue'].includes(extname(entry.name)) ? [target] : []
  })
}

function stripComments(source) {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}

describe('first-party runtime log privacy', () => {
  it('routes all runtime console output through the reviewed safe logger', () => {
    const files = [
      ...FIRST_PARTY_PATHS.flatMap((path) => runtimeFiles(join(ROOT, path))),
      ...ROOT_FILES.map((file) => join(ROOT, file)),
    ]
    const violations = files
      .filter((file) => file !== ALLOWED_CONSOLE_FILE)
      .filter((file) => /console\.(?:log|info|warn|error|debug)\s*\(/.test(
        stripComments(readFileSync(file, 'utf8')),
      ))
      .map((file) => relative(ROOT, file).replaceAll('\\', '/'))

    expect(violations).toEqual([])
  })
})
