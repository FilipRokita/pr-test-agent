import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useTodoStatsQuery } from '../hooks/useTodoStatsQuery'
import type { TodoStats } from '../types'
import { TodoStatsPanel } from './TodoStatsPanel'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('../hooks/useTodoStatsQuery', () => ({ useTodoStatsQuery: vi.fn() }))

type StatsQuery = ReturnType<typeof useTodoStatsQuery>

function mockQuery(state: Partial<StatsQuery>) {
  vi.mocked(useTodoStatsQuery).mockReturnValue({
    isPending: false,
    isError: false,
    data: undefined,
    ...state,
  } as unknown as StatsQuery)
}

function mockStats(data: TodoStats) {
  mockQuery({ data })
}

beforeEach(() => vi.clearAllMocks())

it('shows a loading message while statistics are pending', () => {
  mockQuery({ isPending: true })
  render(<TodoStatsPanel />)
  expect(screen.getByText('Loading statistics…')).toBeVisible()
  expect(screen.queryByLabelText('Task statistics')).not.toBeInTheDocument()
})

it('shows an unavailable message when statistics fail to load', () => {
  mockQuery({ isError: true })
  render(<TodoStatsPanel />)
  expect(screen.getByText('Statistics are unavailable.')).toBeVisible()
  expect(screen.queryByLabelText('Task statistics')).not.toBeInTheDocument()
})

it('shows task counts including overdue tasks', () => {
  mockStats({ total: 5, completed: 2, active: 3, overdue: 1 })
  render(<TodoStatsPanel />)
  expect(screen.getByLabelText('Task statistics')).toBeVisible()
  expect(screen.getByText('5 tasks')).toBeVisible()
  expect(screen.getByText('3 to do')).toBeVisible()
  expect(screen.getByText('2 completed')).toBeVisible()
  expect(screen.getByText('1 overdue')).toBeVisible()
})

it('uses the singular label and hides the overdue badge without overdue tasks', () => {
  mockStats({ total: 1, completed: 0, active: 1, overdue: 0 })
  render(<TodoStatsPanel />)
  expect(screen.getByText('1 task')).toBeVisible()
  expect(screen.getByText('1 to do')).toBeVisible()
  expect(screen.getByText('0 completed')).toBeVisible()
  expect(screen.queryByText(/overdue/)).not.toBeInTheDocument()
})
