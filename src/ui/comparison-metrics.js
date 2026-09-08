export function metricDifference(left, right, compatible = true) {
  if (left == null && right == null) return "Unavailable for both";
  if (left == null || right == null) return "Not comparable";
  if (!compatible) return "Not comparable: scopes differ";
  if (typeof left !== "number" || typeof right !== "number") return left === right ? "same" : "different";
  const value = right - left;
  return `${value > 0 ? "+" : ""}${value.toLocaleString()}`;
}
