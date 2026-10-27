import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import type { Todo, TodoStats } from '../types'
import { useCreateTodoMutation } from './useCreateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))

const stats: TodoStats = { total: 1, completed: 0, active: 1, overdue: 0 }

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

it('puts the saved task first in the cached list without duplicating it', async () => {
  const other: Todo = { ...todoFixture, id: 3, title: 'Other' }
  const saved: Todo = { ...todoFixture, title: 'Saved title' }
  client.setQueryData(todoKeys.list, [other, todoFixture])
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(todoFixture))
  expect(todosApi.create).toHaveBeenCalledWith(todoFixture)
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, other])
})

it('starts the cached list with the saved task when nothing is cached', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(todoFixture)
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(todoFixture))
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})

it('marks the cached statistics stale after a task is created', async () => {
  client.setQueryData(todoKeys.stats, stats)
  vi.mocked(todosApi.create).mockResolvedValue(todoFixture)
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(todoFixture))
  expect(client.getQueryState(todoKeys.stats)?.isInvalidated).toBe(true)
})

it('leaves the cache unchanged when creation fails', async () => {
  client.setQueryData(todoKeys.list, [todoFixture])
  client.setQueryData(todoKeys.stats, stats)
  vi.mocked(todosApi.create).mockRejectedValue(new Error('Server down.'))
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() =>
    expect(result.current.mutateAsync(todoFixture)).rejects.toThrow(
      'Server down.',
    ),
  )
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
  expect(client.getQueryState(todoKeys.stats)?.isInvalidated).toBe(false)
})
