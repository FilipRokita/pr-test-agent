import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatDate, isOverdue, selectTodos, validateTodo } from './todos'
import type { Todo, TodoInput } from '../types'

const base: Todo = {
  id: 1,
  title: 'Sprint plan',
  description: '',
  priority: 'medium',
  completed: false,
  due_date: null,
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:00:00Z',
}

describe('validateTodo', () => {
  it.each<[string, Partial<TodoInput>, Record<string, string>]>([
    ['a 120-character title', { title: 'a'.repeat(120) }, {}],
    [
      'a 121-character title',
      { title: 'a'.repeat(121) },
      { title: 'The title must be at most 120 characters.' },
    ],
    [
      'a title padded beyond 120 characters only by spaces',
      { title: ` ${'a'.repeat(120)} ` },
      {},
    ],
    ['a 2000-character description', { description: 'd'.repeat(2000) }, {}],
    [
      'a 2001-character description',
      { description: 'd'.repeat(2001) },
      { description: 'The description must be at most 2000 characters.' },
    ],
    ['a valid leap-day due date', { due_date: '2028-02-29' }, {}],
    [
      'a non-existent due date',
      { due_date: '2026-02-30' },
      { due_date: 'Enter a valid date.' },
    ],
    [
      'a due date without zero padding',
      { due_date: '2026-2-3' },
      { due_date: 'Enter a valid date.' },
    ],
    [
      'an unparseable due date',
      { due_date: '2026-13-45' },
      { due_date: 'Enter a valid date.' },
    ],
  ])('returns the expected errors for %s', (_, overrides, expected) => {
    expect(validateTodo({ ...base, ...overrides })).toEqual(expected)
  })
})

describe('selectTodos', () => {
  it('combines status with a case-insensitive search in the description', () => {
    const matching = { ...base, description: 'Discuss the API' }
    const todos = [
      matching,
      { ...matching, id: 2, completed: true },
      { ...base, id: 3 },
    ]
    expect(selectTodos(todos, 'active', ' api ', 'newest')).toEqual([matching])
  })

  it('returns only completed tasks for the completed filter', () => {
    const done = { ...base, id: 2, completed: true }
    expect(selectTodos([base, done], 'completed', '', 'newest')).toEqual([done])
  })

  it('sorts by priority without changing the source array', () => {
    const high: Todo = { ...base, id: 2, priority: 'high' }
    const todos = [base, high]
    expect(selectTodos(todos, 'all', '', 'priority')).toEqual([high, base])
    expect(todos).toEqual([base, high])
  })

  it('sorts by due date with undated tasks last and newer ids first on ties', () => {
    const undated = { ...base, id: 1 }
    const later = { ...base, id: 2, due_date: '2026-11-02' }
    const soonOld = { ...base, id: 3, due_date: '2026-10-20' }
    const soonNew = { ...base, id: 4, due_date: '2026-10-20' }
    expect(
      selectTodos([undated, later, soonOld, soonNew], 'all', '', 'due'),
    ).toEqual([soonNew, soonOld, later, undated])
  })

  it('sorts newest first by creation time, then by id', () => {
    const older = { ...base, id: 1, created_at: '2026-09-01T12:00:00Z' }
    const sameTime = { ...base, id: 2 }
    const newer = { ...base, id: 3, created_at: '2026-10-05T12:00:00Z' }
    expect(
      selectTodos([older, base, newer, sameTime], 'all', '', 'newest'),
    ).toEqual([newer, sameTime, base, older])
  })
})

describe('isOverdue', () => {
  afterEach(() => vi.useRealTimers())

  it.each<[string, Partial<Todo>, boolean]>([
    ['an active task due yesterday', { due_date: '2026-10-14' }, true],
    ['an active task due today', { due_date: '2026-10-15' }, false],
    [
      'a completed task due yesterday',
      { due_date: '2026-10-14', completed: true },
      false,
    ],
    ['a task without a due date', { due_date: null }, false],
  ])('treats %s as overdue: %s', (_, overrides, expected) => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 15, 0, 30))
    expect(isOverdue({ ...base, ...overrides })).toBe(expected)
  })
})

describe('formatDate', () => {
  it('formats an ISO date as a British day, short month and year', () => {
    expect(formatDate('2026-10-05')).toBe('5 Oct 2026')
  })
})
