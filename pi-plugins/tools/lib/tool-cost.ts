/**
 * Shared cost contract for tool result details.
 *
 * Any tool that incurs costs includes `cost: number` in its details object.
 * The type guard lets callers narrow unknown details at read boundaries
 * without casting.
 */

export interface ToolCostDetails {
  cost: number;
}

export function hasToolCost(v: unknown): v is ToolCostDetails {
  return (
    v != null &&
    typeof v === "object" &&
    "cost" in v &&
    typeof (v as Record<string, unknown>).cost === "number"
  );
}
