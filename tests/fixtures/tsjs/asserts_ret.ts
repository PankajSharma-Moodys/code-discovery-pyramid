export function assertIsString(v: unknown): asserts v is string {}
export function isStr(v: unknown): v is string { return true; }
export function must(v: unknown): asserts v {}
