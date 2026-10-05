export type TrendPoint = {
  /** Milliseconds since the epoch. */
  t: number;
  value: number;
};

export type TrendFormat = "integer" | "level";

const integerFormat = new Intl.NumberFormat("en-US");

export function formatTrendValue(value: number, format: TrendFormat): string {
  return format === "level" ? value.toFixed(2) : integerFormat.format(value);
}
