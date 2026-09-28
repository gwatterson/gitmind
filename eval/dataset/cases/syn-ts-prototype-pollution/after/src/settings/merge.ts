type Json = { [key: string]: unknown };

export function deepMerge(target: Json, source: Json): Json {
  for (const key in source) {
    const value = source[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      if (!target[key] || typeof target[key] !== "object") {
        target[key] = {};
      }
      deepMerge(target[key] as Json, value as Json);
    } else {
      target[key] = value;
    }
  }
  return target;
}
