---
name: write-frontend-tests
description: Conventions and patterns for Vitest + Testing Library unit tests of the Taskly React frontend (components, hooks, API client, utils). Use before writing or editing any *.test.ts or *.test.tsx file under frontend/src.
---

# Frontend unit tests (Vitest, Testing Library)

## Ground rules

- Colocate: `TodoList.tsx` -> `TodoList.test.tsx`; plain modules -> `*.test.ts`.
- Import test APIs explicitly: `import { beforeEach, expect, it, vi } from 'vitest'`.
- Top-level `it('does X when Y', ...)` with sentence names. No `describe` unless the file already uses it.
- Prettier style: no semicolons, single quotes, trailing commas.
- Fixtures: in an existing file, use the fixture that file already uses (for example the local `base` in
  `utils/todos.test.ts`). In a new file, use `todoFixture` from `src/test/todoFixture.ts` and derive
  variants with spreads (`{ ...todoFixture, completed: true }`). Files under `src/test/` are read-only.

## Isolation

- Design system: `vi.mock('<relative>/design-system', () => import('<relative>/design-system/mocks'))`.
  The mocks render native elements and keep accessible names, so query by role.
- Child components of a container: mock them to a minimal element, as `TodosPage.test.tsx` does.
- Hooks used by a component: `vi.mock` the module and set
  `vi.mocked(hook).mockReturnValue({...} as unknown as ReturnType<typeof hook>)`.
- API layer: `vi.mock('../api/todos')` or `vi.mock('../../../lib/http', () => ({ request: vi.fn() }))`.
- `fetch` in `lib/http.ts`: `vi.stubGlobal('fetch', vi.fn())`, restore with `vi.unstubAllGlobals()`.
- Reset between tests: `beforeEach(() => vi.clearAllMocks())` when mocks are shared in a file.

## Patterns

- **Components**: `render`, then `screen.getByRole(role, { name })`; interactions with
  `const user = userEvent.setup()` and `await user.click(...)`; async with `waitFor` or `findBy*`.
  Assert what the user sees and which callback fired with which arguments.
- **React Query hooks**: `renderHook(() => useX(), { wrapper })` where the wrapper provides a new
  `QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })` per test.
  Seed the cache with `client.setQueryData(todoKeys.list, [...])` and assert the cache after
  `act(() => result.current.mutateAsync(...))`.
- **Time**: `vi.useFakeTimers({ shouldAdvanceTime: true })` +
  `vi.setSystemTime(new Date('2026-10-15T12:00:00Z'))` for `useNotice`, `isOverdue`, `formatDate`;
  with user events use `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`, otherwise `waitFor`
  and user-event hang. Restore with `vi.useRealTimers()` in `afterEach`.
- **Pure functions** (`utils/todos.ts`): table-driven `it.each` for boundaries (120/121 characters, invalid
  dates like `2026-02-30`, empty search).


Annotated examples: [reference.md](reference.md).

## Run

`run_tests` with `stack: "frontend"`, `paths` set to the files you touched; `coverage: true` for the
final check. Type errors in test files fail the run.
