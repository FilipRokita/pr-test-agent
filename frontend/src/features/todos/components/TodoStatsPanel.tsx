import { Badge, Text } from '../../../design-system'
import { useTodoStatsQuery } from '../hooks/useTodoStatsQuery'

export function TodoStatsPanel() {
  const stats = useTodoStatsQuery()
  if (stats.isPending) return <Text muted>Loading statistics…</Text>
  if (stats.isError) return <Text muted>Statistics are unavailable.</Text>
  const { total, active, completed, overdue } = stats.data
  return (
    <div className="row compact" aria-label="Task statistics">
      <Text as="span" muted size="small">
        {total} {total === 1 ? 'task' : 'tasks'}
      </Text>
      <Badge variant="info">{active} to do</Badge>
      <Badge variant="success">{completed} completed</Badge>
      {overdue > 0 && <Badge variant="warning">{overdue} overdue</Badge>}
    </div>
  )
}
