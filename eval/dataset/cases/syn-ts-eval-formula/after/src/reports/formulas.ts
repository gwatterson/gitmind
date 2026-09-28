export type Row = Record<string, number>;

export function evaluateFormula(formula: string, row: Row): number {
  const names = Object.keys(row);
  const compute = new Function(...names, `return (${formula});`);
  return Number(compute(...names.map((name) => row[name])));
}
