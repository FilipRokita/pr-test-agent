import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../test/todoFixture'
import { useNotice } from '../../hooks/useNotice'
import { useTodoFilters } from './hooks/useTodoFilters'
import { useTodosBusy } from './hooks/useTodosBusy'
import { useTodosQuery } from './hooks/useTodosQuery'
import { useUpdateTodoMutation } from './hooks/useUpdateTodoMutation'
import type { Todo } from './types'
import { TodosPage } from './TodosPage'

vi.mock('../../design-system', () => import('../../design-system/mocks'))
vi.mock('../../hooks/useNotice', () => ({ useNotice: vi.fn() }))
vi.mock('./hooks/useTodoFilters', () => ({ useTodoFilters: vi.fn() }))
vi.mock('./hooks/useTodosBusy', () => ({ useTodosBusy: vi.fn() }))
vi.mock('./hooks/useTodosQuery', () => ({ useTodosQuery: vi.fn() }))
vi.mock('./hooks/useUpdateTodoMutation', () => ({
  useUpdateTodoMutation: vi.fn(),
}))
vi.mock('./components/TodosHeader', () => ({
  TodosHeader: ({ onCreate }: { onCreate: () => void }) => (
    <button onClick={onCreate}>Header add task</button>
  ),
}))
vi.mock('./components/TodoFilters', () => ({ TodoFilters: () => null }))
vi.mock('./components/TodoList', () => ({
  TodoList: ({
    todos,
    onCreate,
    onToggle,
    onEdit,
    onDelete,
  }: {
    todos: Todo[]
    onCreate: () => void
    onToggle: (todo: Todo) => void
    onEdit: (todo: Todo) => void
    onDelete: (todo: Todo) => void
  }) => (
    <section>
      <button onClick={onCreate}>List add task</button>
      <button onClick={() => onToggle(todos[0])}>Toggle task</button>
      <button onClick={() => onEdit(todos[0])}>Edit task</button>
      <button onClick={() => onDelete(todos[0])}>Delete task</button>
    </section>
  ),
}))
vi.mock('./components/TodoEditor', () => ({
  TodoEditor: ({
    todo,
    onClose,
    onSaved,
  }: {
    todo: Todo | 'new'
    onClose: () => void
    onSaved: (notice: string) => void
  }) => (
    <div role="dialog" aria-label={todo === 'new' ? 'New task' : todo.title}>
      <button onClick={onClose}>Close editor</button>
      <button onClick={() => onSaved('Changes saved.')}>Save editor</button>
    </div>
  ),
}))
vi.mock('./components/DeleteTodoDialog', () => ({
  DeleteTodoDialog: ({
    todo,
    onClose,
    onDeleted,
  }: {
    todo: Todo
    onClose: () => void
    onDeleted: () => void
  }) => (
    <div role="dialog" aria-label={`Delete ${todo.title}`}>
      <button onClick={onClose}>Close deletion</button>
      <button onClick={onDeleted}>Confirm deletion</button>
    </div>
  ),
}))
vi.mock('../../components/SuccessNotice', () => ({ SuccessNotice: () => null }))

const notify = vi.fn()

function setup({
  busy = false,
  mutateAsync = vi.fn(),
}: { busy?: boolean; mutateAsync?: ReturnType<typeof vi.fn> } = {}) {
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [todoFixture],
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: null,
    reset: vi.fn(),
    mutateAsync,
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(busy)
  vi.mocked(useNotice).mockReturnValue({ message: '', notify })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [todoFixture],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  render(<TodosPage />)
  return userEvent.setup()
}

beforeEach(() => vi.clearAllMocks())

it('displays a query failure and resets mutation errors before retrying', async () => {
  const user = userEvent.setup()
  const refetch = vi.fn().mockResolvedValue(undefined)
  const reset = vi.fn()
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [],
    isPending: false,
    isFetching: false,
    isError: true,
    error: new Error('The server is unavailable.'),
    refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: null,
    reset,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(false)
  vi.mocked(useNotice).mockReturnValue({ message: '', notify: vi.fn() })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent(
    'The server is unavailable.',
  )
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1))
  expect(reset).toHaveBeenCalledTimes(1)
  expect(reset.mock.invocationCallOrder[0]).toBeLessThan(
    refetch.mock.invocationCallOrder[0],
  )
})

it.each([
  { completed: true, notice: 'Another task complete. Well done!' },
  { completed: false, notice: 'Task marked as active.' },
])(
  'toggles a task and announces "$notice" from the saved state',
  async ({ completed, notice }) => {
    const mutateAsync = vi.fn().mockResolvedValue({ ...todoFixture, completed })
    const user = setup({ mutateAsync })
    await user.click(screen.getByRole('button', { name: 'Toggle task' }))
    await waitFor(() => expect(notify).toHaveBeenCalledWith(notice))
    expect(mutateAsync).toHaveBeenCalledWith({
      id: todoFixture.id,
      input: { completed: !todoFixture.completed },
    })
  },
)

it('does not toggle a task while another task mutation is running', async () => {
  const mutateAsync = vi.fn()
  const user = setup({ busy: true, mutateAsync })
  await user.click(screen.getByRole('button', { name: 'Toggle task' }))
  expect(mutateAsync).not.toHaveBeenCalled()
  expect(notify).not.toHaveBeenCalled()
})

it('does not announce success when toggling fails', async () => {
  const mutateAsync = vi.fn().mockRejectedValue(new Error('Conflict.'))
  const user = setup({ mutateAsync })
  await user.click(screen.getByRole('button', { name: 'Toggle task' }))
  await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
  expect(notify).not.toHaveBeenCalled()
})

it.each(['Header add task', 'List add task'])(
  'opens the new task editor from "%s" and closes it without a notice',
  async (button) => {
    const user = setup()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: button }))
    expect(screen.getByRole('dialog', { name: 'New task' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Close editor' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(notify).not.toHaveBeenCalled()
  },
)

it('closes the task editor and announces the editor notice after saving', async () => {
  const user = setup()
  await user.click(screen.getByRole('button', { name: 'Edit task' }))
  expect(screen.getByRole('dialog', { name: todoFixture.title })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Save editor' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(notify).toHaveBeenCalledWith('Changes saved.')
})

it('closes the deletion dialog and announces the deletion', async () => {
  const user = setup()
  await user.click(screen.getByRole('button', { name: 'Delete task' }))
  expect(
    screen.getByRole('dialog', { name: `Delete ${todoFixture.title}` }),
  ).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Confirm deletion' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(notify).toHaveBeenCalledWith('Task deleted.')
})

it('closes the deletion dialog on cancel without a notice', async () => {
  const user = setup()
  await user.click(screen.getByRole('button', { name: 'Delete task' }))
  await user.click(screen.getByRole('button', { name: 'Close deletion' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(notify).not.toHaveBeenCalled()
})
