import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'
import { useTodoFilters } from './useTodoFilters'

it('starts with all tasks newest first and narrows the visible tasks as filters change', () => {
  const older: Todo = {
    ...todoFixture,
    id: 1,
    title: 'Write report',
    completed: true,
    created_at: '2026-09-01T12:00:00Z',
  }
  const { result } = renderHook(() => useTodoFilters([older, todoFixture]))
  expect(result.current).toMatchObject({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [todoFixture, older],
  })
  act(() => result.current.setFilter('completed'))
  expect(result.current.visible).toEqual([older])
  act(() => {
    result.current.setFilter('all')
    result.current.setSearch('demo')
  })
  expect(result.current.visible).toEqual([todoFixture])
})

it('re-sorts the visible tasks when the sort changes', () => {
  const urgent: Todo = {
    ...todoFixture,
    id: 1,
    priority: 'high',
    created_at: '2026-09-01T12:00:00Z',
  }
  const { result } = renderHook(() => useTodoFilters([todoFixture, urgent]))
  act(() => result.current.setSort('priority'))
  expect(result.current.sort).toBe('priority')
  expect(result.current.visible).toEqual([urgent, todoFixture])
})
