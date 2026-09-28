/* eslint-disable @typescript-eslint/no-explicit-any */
import {
  isFunction,
  isNotUndefined,
  isObjectLoose,
  isObjectPlain
} from '@phun-ky/typeof';

/* node:coverage disable */
/**
 * Customizer function used by {@link mergeWith} to override merge behaviour.
 *
 * If the customizer returns `undefined`, {@link mergeWith} falls back to its default
 * deep-merge rules. Any other return value will be assigned to the destination key.
 *
 * @param objValue - Current value on the destination (`object`) for `key`.
 * @param srcValue - Incoming value from the current `source` for `key`.
 * @param key - Property key being merged (string or symbol).
 * @param object - Destination object being mutated/merged into.
 * @param source - Current source object being merged from.
 * @param stack - A `WeakMap` used internally to prevent infinite recursion on circular references.
 * @returns The value to assign for this key, or `undefined` to use default merge behaviour.
 *
 * @example
 * ```ts
 * import { mergeWith, type MergeWithCustomizer } from "./mergeWith";
 *
 * const concatArrays: MergeWithCustomizer = (objValue, srcValue) => {
 *   if (Array.isArray(objValue) && Array.isArray(srcValue)) {
 *     return objValue.concat(srcValue);
 *   }
 *   return undefined;
 * };
 *
 * const a = { list: [1] };
 * const b = { list: [2] };
 *
 * mergeWith(a, b, concatArrays);
 * // => { list: [1, 2] }
 * ```
 */
/* node:coverage enable */
export type MergeWithCustomizer = (
  objValue: unknown,
  srcValue: unknown,
  key: string | symbol,
  object: Record<PropertyKey, unknown>,
  source: Record<PropertyKey, unknown>,
  stack: WeakMap<object, object>
) => unknown;

type UnionToIntersection<U> = (U extends any ? (k: U) => void : never) extends (
  k: infer I
) => void
  ? I
  : never;

type MergeResult<T, S extends readonly any[]> = T &
  UnionToIntersection<S[number]>;

/**
 * Deep-merges one or more source objects into a destination object, with optional customization.
 *
 * This is a "vanilla TS" alternative to lodash's `mergeWith` with a deliberately conservative
 * default strategy:
 *
 * - **Mutates** and returns the destination `object`.
 * - Enumerates **own enumerable string keys** and **own enumerable symbol keys** from each source.
 * - When both destination and source values are **plain objects**, merges recursively.
 * - When the source value is a **plain object** but the destination is not, creates `{}` and merges into it.
 * - All other value types (arrays, dates, maps, sets, functions, primitives, class instances, etc.)
 *   are assigned by **replacement** unless the customizer handles them.
 * - Circular references in **sources** are prevented from causing infinite recursion via a `WeakMap` stack.
 *
 * @typeParam T - Destination object type.
 * @typeParam S - Tuple/array of source object types.
 *
 * @param object - Destination object to merge into (will be mutated).
 * @param args - One or more source objects, optionally followed by a {@link MergeWithCustomizer}.
 * @returns The same `object` reference, now merged with all sources.
 *
 * @remarks
 * - The default merge behaviour only recurses into "plain objects", as determined by `isObjectPlain`.
 * - "Loose objects" are guarded using `isObjectLoose` to avoid attempting to merge non-object sources.
 * - If you want lodash-like array merging semantics (concat or index-wise), implement it via `customizer`.
 *
 * @example
 * ```ts
 * const target = { a: { x: 1 }, b: 1 };
 * const source = { a: { y: 2 }, b: 2 };
 *
 * mergeWith(target, source);
 * // => { a: { x: 1, y: 2 }, b: 2 }
 * // target is mutated
 * ```
 *
 * @example
 * ```ts
 * const target = { list: [1] };
 * const source = { list: [2] };
 *
 * mergeWith(target, source);
 * // => { list: [2] }  (arrays replace by default)
 * ```
 *
 * @example
 * ```ts
 * const concatArrays: MergeWithCustomizer = (objValue, srcValue) => {
 *   if (Array.isArray(objValue) && Array.isArray(srcValue)) {
 *     return objValue.concat(srcValue);
 *   }
 * };
 *
 * mergeWith({ list: [1] }, { list: [2] }, concatArrays);
 * // => { list: [1, 2] }
 * ```
 */

export function mergeWith<
  T extends Record<PropertyKey, any>,
  S extends readonly Record<PropertyKey, any>[]
>(object: T, ...sources: S): MergeResult<T, S>;

export function mergeWith<
  T extends Record<PropertyKey, any>,
  S extends readonly Record<PropertyKey, any>[]
>(
  object: T,
  ...args: [...sources: S, customizer: MergeWithCustomizer]
): MergeResult<T, S>;

export function mergeWith(
  object: Record<PropertyKey, unknown>,
  ...args: (Record<PropertyKey, unknown> | MergeWithCustomizer)[]
): Record<PropertyKey, unknown> {
  const maybeCustomizer = args.at(-1);
  const customizer = isFunction(maybeCustomizer)
    ? (maybeCustomizer as MergeWithCustomizer)
    : undefined;
  const sources = (customizer ? args.slice(0, -1) : args) as Record<
    PropertyKey,
    unknown
  >[];
  const stack = new WeakMap<object, object>();

  for (const source of sources) {
    baseMerge(
      object as Record<PropertyKey, unknown>,
      source,
      customizer,
      stack
    );
  }

  return object as any;
}

/**
 * Internal recursive merge implementation used by {@link mergeWith}.
 *
 * @param target - Destination object that is being mutated.
 * @param source - Current source object being merged in.
 * @param customizer - Optional custom merge override.
 * @param stack - Tracks visited source objects to avoid infinite recursion.
 */
const baseMerge = (
  target: Record<PropertyKey, unknown>,
  source: Record<PropertyKey, unknown>,
  customizer: MergeWithCustomizer | undefined,
  stack: WeakMap<object, object>
): void => {
  if (!isObjectLoose(source)) return;

  for (const key of ownKeys(source)) {
    const srcValue = (source as any)[key];
    const objValue = (target as any)[key];
    const customized = customizer?.(
      objValue,
      srcValue,
      key,
      target,
      source,
      stack
    );

    if (isNotUndefined(customized)) {
      (target as any)[key] = customized;
      continue;
    }

    // Both are plain objects: merge into existing destination object.
    if (isObjectPlain(objValue) && isObjectPlain(srcValue)) {
      // If we've seen this src object before, reuse the prior destination.
      const cached = stack.get(srcValue as object);

      if (cached) {
        (target as any)[key] = cached;
        continue;
      }

      // Cache before recursing to handle cycles.
      stack.set(srcValue as object, objValue as object);

      baseMerge(
        objValue as Record<PropertyKey, unknown>,
        srcValue as Record<PropertyKey, unknown>,
        customizer,
        stack
      );
      continue;
    }

    // Source is a plain object but destination isn't: create destination object and merge into it.
    if (isObjectPlain(srcValue)) {
      const cached = stack.get(srcValue as object);

      if (cached) {
        (target as any)[key] = cached;
        continue;
      }

      const next: Record<PropertyKey, unknown> = isObjectPlain(objValue)
        ? (objValue as Record<PropertyKey, unknown>)
        : {};

      (target as any)[key] = next;

      // Cache before recursing to handle cycles and repeated refs.
      stack.set(srcValue as object, next as object);

      baseMerge(
        next,
        srcValue as Record<PropertyKey, unknown>,
        customizer,
        stack
      );
      continue;
    }

    // Arrays, primitives, dates, maps, sets, functions, etc. are assigned by replacement
    (target as any)[key] = srcValue;
  }
};
/**
 * Returns enumerable own property keys (string + symbol) for an object.
 *
 * This mirrors lodash's behaviour of considering both string keys and symbol keys,
 * but only those that are enumerable.
 *
 * @param obj - Object to inspect.
 * @returns Array of enumerable own keys (strings and symbols).
 *
 * @example
 * ```ts
 * const sym = Symbol("x");
 * const o = { a: 1, [sym]: 2 };
 * Object.defineProperty(o, "hidden", { value: 3, enumerable: false });
 *
 * ownKeys(o);
 * // => ["a", Symbol("x")]
 * ```
 */
const ownKeys = (obj: object): (string | symbol)[] => [
  ...Object.keys(obj),
  ...Object.getOwnPropertySymbols(obj).filter((s) =>
    Object.prototype.propertyIsEnumerable.call(obj, s)
  )
];
