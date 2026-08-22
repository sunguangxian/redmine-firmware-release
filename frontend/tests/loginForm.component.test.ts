import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import LoginView from '../src/views/LoginView.vue'

vi.mock('../src/api/http', () => ({
  errorMessage: (error: unknown) => String(error),
  login: vi.fn(),
}))

describe('LoginView password form', () => {
  it('renders browser password-manager semantics in the mounted component', () => {
    const wrapper = shallowMount(LoginView, { props: { version: 'test' } })
    const form = wrapper.get('form#login-form')
    const username = wrapper.get('input#login-username')
    const password = wrapper.get('input#current-password')

    expect(form.attributes()).toMatchObject({ action: '/login', method: 'post', autocomplete: 'on' })
    expect(username.attributes()).toMatchObject({ name: 'username', autocomplete: 'username' })
    expect(password.attributes()).toMatchObject({ name: 'password', autocomplete: 'current-password', type: 'password' })
    expect(wrapper.get('button#login-submit').attributes('type')).toBe('submit')
  })
})
