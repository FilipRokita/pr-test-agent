import { QueryClient, useQueryClient } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { useTheme } from 'styled-components'
import { expect, it, vi } from 'vitest'
import { theme } from '../design-system'
import { AppProviders } from './AppProviders'

vi.mock('../design-system', () => import('../design-system/mocks'))

function Probe({ client }: { client: QueryClient }) {
  const current = useQueryClient()
  const activeTheme = useTheme()
  return (
    <p>
      {current === client ? 'given client' : 'other client'},{' '}
      {activeTheme === theme ? 'app theme' : 'other theme'}
    </p>
  )
}

it('renders children with the given query client and the app theme', () => {
  const client = new QueryClient()
  render(
    <AppProviders client={client}>
      <Probe client={client} />
    </AppProviders>,
  )
  expect(screen.getByText('given client, app theme')).toBeVisible()
})
