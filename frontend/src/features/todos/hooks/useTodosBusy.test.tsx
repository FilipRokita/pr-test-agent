import {
  QueryClient,
  QueryClientProvider,
  useMutation,
} from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { expect, it } from 'vitest'
import { useTodosBusy } from './useTodosBusy'

it('is busy only while a task mutation is pending', async () => {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  let finish = () => {}
  const { result } = renderHook(
    () => ({
      busy: useTodosBusy(),
      other: useMutation({
        mutationKey: ['settings', 'save'],
        mutationFn: () => new Promise<void>(() => {}),
      }),
      todo: useMutation({
        mutationKey: ['todos', 'update'],
        mutationFn: () =>
          new Promise<void>((resolve) => {
            finish = resolve
          }),
      }),
    }),
    { wrapper },
  )
  expect(result.current.busy).toBe(false)
  act(() => result.current.other.mutate())
  await waitFor(() => expect(result.current.other.isPending).toBe(true))
  expect(result.current.busy).toBe(false)
  act(() => result.current.todo.mutate())
  await waitFor(() => expect(result.current.busy).toBe(true))
  act(() => finish())
  await waitFor(() => expect(result.current.busy).toBe(false))
})
