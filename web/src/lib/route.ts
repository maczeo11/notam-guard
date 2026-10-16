/** The five graph nodes, in the order a request passes through them. */
export type NodeId = 'router' | 'validator' | 'retriever' | 'safety' | 'responder'

export const NODES: { id: NodeId; label: string; hint: string }[] = [
  { id: 'router', label: 'Router', hint: 'Picks which checks to run' },
  { id: 'validator', label: 'Validator', hint: 'Plain-Python distance and altitude checks' },
  { id: 'retriever', label: 'Retriever', hint: 'Fetches the text of the rules that were applied' },
  { id: 'safety', label: 'Safety', hint: 'Sets the verdict and opens a ticket' },
  { id: 'responder', label: 'Responder', hint: 'Words the sentence you read' },
]

/** Which nodes ran for a route. Mirrors `_after_router` and `_after_validator` in src/graph.py. */
export function nodesRun(action: string): Set<NodeId> {
  const all = new Set<NodeId>(NODES.map(n => n.id))
  if (action === 'act') all.delete('retriever')
  if (action === 'retrieve') all.delete('validator')
  return all
}

export const ROUTE_COPY: Record<string, { name: string; detail: string }> = {
  both: {
    name: 'Full check',
    detail: 'The plan was validated, then the text of each rule applied was retrieved and checked.',
  },
  act: {
    name: 'Geometry only',
    detail: 'The plan was validated, but nothing was retrieved to back it up, so a clear flight is held.',
  },
  retrieve: {
    name: 'Retrieval only',
    detail: 'The validator never ran, so nothing was cleared and the flight is held.',
  },
}

export function routeCopy(action: string) {
  return ROUTE_COPY[action] ?? { name: action || 'Unknown route', detail: '' }
}
