import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'
import { TodoList } from './TodoList'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('./TodoEmptyState', () => ({
  TodoEmptyState: () => <p>Empty task list</p>,
}))
vi.mock('./TodoItem', () => ({
  TodoItem: ({
    todo,
    onToggle,
    onEdit,
    onDelete,
  }: {
    todo: Todo
    onToggle: () => void
    onEdit: () => void
    onDelete: () => void
  }) => (
    <li>
      {todo.title}
      <button onClick={onToggle}>Toggle {todo.title}</button>
      <button onClick={onEdit}>Edit {todo.title}</button>
      <button onClick={onDelete}>Delete {todo.title}</button>
    </li>
  ),
}))

const props = {
  todos: [] as Todo[],
  hasTodos: false,
  failed: false,
  busy: false,
  onCreate: vi.fn(),
  onToggle: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
}

it('shows loading feedback before showing an empty list', () => {
  const { rerender } = render(<TodoList {...props} loading />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading your tasks…')
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
  rerender(<TodoList {...props} loading={false} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('Empty task list')).toBeVisible()
})

it('shows an unavailable message instead of the empty state when loading failed', () => {
  render(<TodoList {...props} loading={false} failed />)
  expect(
    screen.getByRole('heading', {
      name: 'The task list is temporarily unavailable',
    }),
  ).toBeVisible()
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
})

it('keeps listing cached tasks after a failed refetch and forwards each action with its task', async () => {
  const user = userEvent.setup()
  const second: Todo = { ...todoFixture, id: 8, title: 'Review notes' }
  const onToggle = vi.fn()
  const onEdit = vi.fn()
  const onDelete = vi.fn()
  render(
    <TodoList
      {...props}
      todos={[todoFixture, second]}
      hasTodos
      failed
      loading={false}
      onToggle={onToggle}
      onEdit={onEdit}
      onDelete={onDelete}
    />,
  )
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  await user.click(screen.getByRole('button', { name: 'Toggle Review notes' }))
  await user.click(screen.getByRole('button', { name: 'Edit Review notes' }))
  await user.click(
    screen.getByRole('button', { name: `Delete ${todoFixture.title}` }),
  )
  expect(onToggle).toHaveBeenCalledWith(second)
  expect(onEdit).toHaveBeenCalledWith(second)
  expect(onDelete).toHaveBeenCalledWith(todoFixture)
})
