export function parse(x: string): string;
export function parse(x: number): number;
export function parse(x: any): any { return x; }
export class C {
  m(a: string): void;
  m(a: number): void;
  m(a: any): void {}
}
