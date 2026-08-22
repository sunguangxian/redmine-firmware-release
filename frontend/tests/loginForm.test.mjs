import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('../src/views/LoginView.vue', import.meta.url), 'utf8')

test('password login exposes stable password-manager form semantics', () => {
  assert.match(source, /<form[\s\S]*id="login-form"[\s\S]*name="login"[\s\S]*action="\/login"[\s\S]*method="post"[\s\S]*autocomplete="on"/)
  assert.match(source, /id="login-username"[\s\S]*name="username"[\s\S]*autocomplete="username"/)
  assert.match(source, /id="current-password"[\s\S]*name="password"[\s\S]*autocomplete="current-password"/)
  assert.match(source, /<button id="login-submit" type="submit"/)
})

test('password login keeps a native navigation fallback for insecure LAN origins', () => {
  assert.match(source, /if \(!window\.isSecureContext[\s\S]*return[\s\S]*event\.preventDefault\(\)/)
  assert.match(source, /navigator\.credentials\.store\(new PasswordCredential\(nativeForm\)\)/)
})

test('SPA login signals successful submission after removing the password form', () => {
  assert.match(source, /emit\('logged-in', data\)[\s\S]*await nextTick\(\)[\s\S]*window\.history\.pushState/)
})
