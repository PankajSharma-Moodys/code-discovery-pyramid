export abstract class Shape {
  #secret = 1;
  protected abstract area(): number;
  static readonly ORIGIN: string = 'o';
  get size(): number { return 1; }
  set size(v: number) {}
  private opt?: string;
}
