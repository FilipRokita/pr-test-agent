import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { request } from './http'

const fetchMock = vi.fn()

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

it('prefixes the API path, merges JSON headers and returns the parsed body', async () => {
  fetchMock.mockResolvedValue(jsonResponse(200, [{ id: 1 }]))
  await expect(
    request('/todos', { method: 'POST', headers: { 'X-Trace': 'abc' } }),
  ).resolves.toEqual([{ id: 1 }])
  expect(fetchMock).toHaveBeenCalledWith('/api/todos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Trace': 'abc' },
  })
})

it('resolves to undefined for a 204 response without reading a body', async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
  await expect(
    request('/todos/1', { method: 'DELETE' }),
  ).resolves.toBeUndefined()
})

it('replaces a network failure with a connection message', async () => {
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
  await expect(request('/todos')).rejects.toThrow(
    'Cannot connect to the server. Please try again.',
  )
})

it('rethrows the original error when the request was aborted', async () => {
  const controller = new AbortController()
  controller.abort()
  const abortError = new DOMException('Aborted', 'AbortError')
  fetchMock.mockRejectedValue(abortError)
  await expect(request('/todos', { signal: controller.signal })).rejects.toBe(
    abortError,
  )
})

it.each([
  {
    response: jsonResponse(422, { detail: [{ msg: 'too long' }] }),
    message:
      'Check the task details: title up to 120 characters, description up to 2000 characters, and a valid due date.',
  },
  {
    response: jsonResponse(404, { detail: 'Task not found.' }),
    message: 'Task not found.',
  },
  {
    response: jsonResponse(500, { detail: { code: 'boom' } }),
    message: 'The operation failed. Please try again.',
  },
  {
    response: new Response('<html>Bad gateway</html>', { status: 502 }),
    message: 'The operation failed. Please try again.',
  },
])(
  'rejects a $response.status response with "$message"',
  async ({ response, message }) => {
    fetchMock.mockResolvedValue(response)
    await expect(request('/todos')).rejects.toThrow(message)
  },
)
