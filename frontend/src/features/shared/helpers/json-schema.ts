/** Utilità sui JSON Schema (generati da Pydantic con `$defs`/`$ref`) per l'editor YAML. */

type Json = Record<string, unknown>

/**
 * Sostituisce i `$ref` locali (`#/$defs/X`, `#/definitions/X`) con la definizione, fino a `maxDepth` annidamenti dello stesso riferimento
 * (gli schemi ricorsivi, es. `if` dentro `then`, si fermano lì). Serve perché `codemirror-json-schema` non completa i valori `enum` dietro un `$ref`.
 * @param schema schema con `$defs`
 * @param maxDepth quante volte lo stesso `$ref` può comparire lungo un ramo
 * @returns un nuovo schema senza `$defs` né `$ref` (tranne oltre il limite, dove il ramo è lasciato libero)
 */
export function inlineRefs(schema: object, maxDepth = 3): object {
  const root = schema as Json
  const defs = { ...(root.$defs as Json | undefined), ...(root.definitions as Json | undefined) }
  /** Espande un nodo; `seen` conta i `$ref` già attraversati su questo ramo. */
  function walk(node: unknown, seen: Record<string, number>): unknown {
    if (Array.isArray(node)) return node.map((n) => walk(n, seen))
    if (node === null || typeof node !== 'object') return node
    const obj = node as Json
    if (typeof obj.$ref === 'string') {
      const name = obj.$ref.replace(/^#\/(\$defs|definitions)\//, '')
      const target = defs[name]
      if (!target || (seen[name] ?? 0) >= maxDepth) return {}
      const { $ref: _ref, ...rest } = obj
      return { ...(walk(target, { ...seen, [name]: (seen[name] ?? 0) + 1 }) as Json), ...(walk(rest, seen) as Json) }
    }
    return Object.fromEntries(Object.entries(obj).filter(([k]) => k !== '$defs' && k !== 'definitions').map(([k, v]) => [k, walk(v, seen)]))
  }
  return walk(root, {}) as object
}
