import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useTodoStatsQuery } from '../hooks/useTodoStatsQuery'
import type { TodoStats } from '../types'
import { TodoStatsPanel } from './TodoStatsPanel'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('../hooks/useTodoStatsQuery', () => ({ useTodoStatsQuery: vi.fn() }))

beforeEach(() => vi.clearAllMocks())

function mockStats(state: object) {
  vi.mocked(useTodoStatsQuery).mockReturnValue(
    state as unknown as ReturnType<typeof useTodoStatsQuery>,
  )
}

function mockLoaded(data: TodoStats) {
  mockStats({ isPending: false, isError: false, data })
}

it('shows a loading message while statistics are pending', () => {
  mockStats({ isPending: true, isError: false, data: undefined })
  render(<TodoStatsPanel />)
  expect(screen.getByText('Loading statistics…')).toBeVisible()
  expect(screen.queryByLabelText('Task statistics')).not.toBeInTheDocument()
})

it('shows an unavailable message when statistics fail to load', () => {
  mockStats({ isPending: false, isError: true, data: undefined })
  render(<TodoStatsPanel />)
  expect(screen.getByText('Statistics are unavailable.')).toBeVisible()
  expect(screen.queryByLabelText('Task statistics')).not.toBeInTheDocument()
})

it('shows the total, to do, completed and overdue counts', () => {
  mockLoaded({ total: 5, completed: 2, active: 3, overdue: 1 })
  render(<TodoStatsPanel />)
  expect(screen.getByLabelText('Task statistics')).toBeVisible()
  expect(screen.getByText('5 tasks')).toBeVisible()
  expect(screen.getByText('3 to do')).toBeVisible()
  expect(screen.getByText('2 completed')).toBeVisible()
  expect(screen.getByText('1 overdue')).toBeVisible()
})

it('uses the singular for one task and hides the overdue count when nothing is overdue', () => {
  mockLoaded({ total: 1, completed: 0, active: 1, overdue: 0 })
  render(<TodoStatsPanel />)
  expect(screen.getByText('1 task')).toBeVisible()
  expect(screen.queryByText(/overdue/)).not.toBeInTheDocument()
})
