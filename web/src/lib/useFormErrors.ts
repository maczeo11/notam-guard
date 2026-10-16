import { useState } from 'react'
import type { FlightPlan } from './api'
import { validatePlan, type PlanErrors } from './plan'

export type Field = keyof PlanErrors

/**
 * Validation that stays quiet until a field has been left or a check was asked for,
 * so a visitor is not shown an error for a field they have not finished typing.
 */
export function useFormErrors(plan: FlightPlan) {
  const [touched, setTouched] = useState<Set<Field>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const errors: PlanErrors = validatePlan(plan)

  const shown = (field: Field) => (submitted || touched.has(field) ? errors[field] : undefined)
  const touch = (field: Field) => setTouched(current => (current.has(field) ? current : new Set(current).add(field)))

  /** True when the plan is valid. Otherwise reveals every error and focuses the first bad field. */
  function submit(): boolean {
    setSubmitted(true)
    const [first] = Object.keys(errors)       // validatePlan adds keys in on-screen order
    if (!first) return true
    const element = document.querySelector<HTMLElement>(`[name="${first}"]`)
    const section = element?.closest('details')
    if (section) section.open = true           // a hidden field cannot take focus
    element?.focus()
    return false
  }

  return { errors, shown, touch, submit, hasErrors: Object.keys(errors).length > 0 }
}
