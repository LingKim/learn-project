import type { DefinitionView } from "./api";

/** OpenAPI的注册契约是未知结构，先收窄再读字段，不能把它当作另一套手写DTO。 */
export function registeredContractRecord(
  definition: DefinitionView,
): Record<string, unknown> | null {
  const value: unknown = definition.registered_contract;
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function registeredContractText(definition: DefinitionView, field: string): string | null {
  const value = registeredContractRecord(definition)?.[field];
  return typeof value === "string" ? value : null;
}
