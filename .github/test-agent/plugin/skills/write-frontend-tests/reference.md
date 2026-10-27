# Frontend test examples

Every example runs in this repository. Copy the shape, not the names.

## A component with mocked hooks and design system (from `TodoEditor.test.tsx`)

```tsx
vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('../hooks/useCreateTodoMutation', () => ({ useCreateTodoMutation: vi.fn() }))

vi.mocked(useCreateTodoMutation).mockReturnValue({
  isPending: false,
  error: null,
  mutateAsync: create,
} as unknown as ReturnType<typeof useCreateTodoMutation>)

render(<TodoEditor todo="new" busy={false} onClose={vi.fn()} onSaved={onSaved} />)
await user.click(screen.getByRole('button', { name: 'Submit form' }))
await waitFor(() => expect(onSaved).toHaveBeenCalledWith('New task added.'))
```

Why: the child form is mocked to one button, so the test is about the editor's behaviour. The accessible name
finds the element, as a user would.

## A container with mocked children (from `TodosPage.test.tsx`)

Mock each child to a minimal element, mock the hooks with `vi.mocked(...).mockReturnValue(...)`, then assert the
user-visible effect and the call order:

```tsx
expect(reset.mock.invocationCallOrder[0]).toBeLessThan(refetch.mock.invocationCallOrder[0])
```

## A React Query mutation: a fresh client per test, seed the cache, assert the cache

```tsx
function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

it('removes the deleted task from the cached list', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  const { client, wrapper } = createWrapper()
  client.setQueryData(todoKeys.list, [todoFixture, { ...todoFixture, id: 8 }])
  const { result } = renderHook(() => useDeleteTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(7))
  expect(client.getQueryData(todoKeys.list)).toEqual([{ ...todoFixture, id: 8 }])
})
```

Restore globals in `afterEach(() => vi.unstubAllGlobals())`.

## The HTTP client: stub `fetch`, assert the mapped error

```tsx
vi.stubGlobal(
  'fetch',
  vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [] }), { status: 422 })),
)
await expect(request('/todos')).rejects.toThrow('Check the task details')
```

Other branches worth a case each: a network failure (`fetch` rejects), `204` returns `undefined`, a string
`detail` becomes the message, an aborted signal rethrows the original error.

## Time: fake timers that still let async work finish

```tsx
vi.useFakeTimers({ shouldAdvanceTime: true })
const { result } = renderHook(() => useNotice())
act(() => result.current.notify('Saved'))
expect(result.current.message).toBe('Saved')
act(() => {
  vi.advanceTimersByTime(4000)
})
expect(result.current.message).toBe('')
```

Restore with `vi.useRealTimers()` in `afterEach`.
