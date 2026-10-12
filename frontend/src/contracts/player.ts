import Ajv2020 from 'ajv/dist/2020'

import playerSchema from '../../player.schema.json'
import slidesSchema from '../../slides.schema.json'
import type { PlayerJson } from './player.types'

const ajv = new Ajv2020({ allErrors: true, strict: false })
ajv.addSchema(slidesSchema)
ajv.addSchema(playerSchema)

const validate = ajv.compile<PlayerJson>(playerSchema)

export function isPlayerJson(value: unknown): value is PlayerJson {
  return validate(value) === true
}
