import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import type { Todo } from '../types'
import { useUpdateTodoMutation } from './useUpdateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { update: vi.fn() } }))

let client: QueryClient

beforeEach(() => {
  vi.clearAllMocks()
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
})

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

it('replaces only the saved task in the cached list, keeping its position', async () => {
  const first: Todo = { ...todoFixture, id: 1, title: 'First' }
  const last: Todo = { ...todoFixture, id: 9, title: 'Last' }
  const saved: Todo = { ...todoFixture, completed: true }
  client.setQueryData(todoKeys.list, [first, todoFixture, last])
  vi.mocked(todosApi.update).mockResolvedValue(saved)
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({
      id: todoFixture.id,
      input: { completed: true },
    }),
  )
  expect(todosApi.update).toHaveBeenCalledWith(todoFixture.id, {
    completed: true,
  })
  expect(client.getQueryData(todoKeys.list)).toEqual([first, saved, last])
})

it('does not create a cached list when none was loaded', async () => {
  vi.mocked(todosApi.update).mockResolvedValue(todoFixture)
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({ id: todoFixture.id, input: { title: 'x' } }),
  )
  expect(client.getQueryData(todoKeys.list)).toBeUndefined()
})
