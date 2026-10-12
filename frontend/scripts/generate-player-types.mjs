import { readFile, writeFile } from 'node:fs/promises'
import { compile } from 'json-schema-to-typescript'

const [playerSchema, slidesSchema] = await Promise.all([
  readFile(new URL('../player.schema.json', import.meta.url), 'utf8').then(JSON.parse),
  readFile(new URL('../slides.schema.json', import.meta.url), 'utf8').then(JSON.parse),
])

// Resolve the cross-file slide reference and turn the schema's if/then rules into a TS union.
const lecture = structuredClone(slidesSchema.$defs.lecture)
const baseSlide = slidesSchema.$defs.slide
const playerSlide = structuredClone(playerSchema.$defs.slide)
delete playerSlide.$ref

const variantProperties = new Set(['image', 'width', 'height', 'markdown', 'code', 'language'])
const commonProperties = Object.fromEntries(
  Object.entries({ ...baseSlide.properties, ...playerSlide.properties }).filter(
    ([name]) => name !== 'kind' && !variantProperties.has(name),
  ),
)
const commonRequired = [...new Set([
  ...(baseSlide.required ?? []).filter((name) => name !== 'kind'),
  ...(playerSlide.required ?? []),
])]
const slideVariants = ['image', 'markdown', 'code'].map((kind) => {
  const condition = baseSlide.allOf.find((rule) => rule.if.properties.kind.const === kind)
  const required = condition.then.required
  const fields = Object.fromEntries(required.map((name) => [name, baseSlide.properties[name]]))
  return {
    title: `${kind[0].toUpperCase()}${kind.slice(1)}Slide`,
    type: 'object',
    additionalProperties: false,
    properties: { ...commonProperties, kind: { const: kind }, ...fields },
    required: [...commonRequired, 'kind', ...required],
  }
})

const schema = {
  ...lecture,
  title: 'PlayerJson',
  required: [...new Set([...(lecture.required ?? []), ...(playerSchema.required ?? [])])],
  properties: { ...lecture.properties, ...playerSchema.properties },
  additionalProperties: false,
}
schema.properties.slides.items = { oneOf: slideVariants }

const declaration = await compile(schema, 'PlayerJson', { bannerComment: '/** Generated from player.schema.json. */' })
await writeFile(new URL('../src/contracts/player.types.ts', import.meta.url), declaration)
