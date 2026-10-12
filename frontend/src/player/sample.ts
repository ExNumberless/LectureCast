import fixture from '../contracts/player.json'
import { isPlayerJson } from '../contracts/player'
import { fromPlayerJson } from './timeline'
import type { PlayerLecture } from './timeline'

/**
 * Until the backend serves each lecture's player.json, the player page plays the contract fixture.
 * Its paths resolve against the fixture's own location, like a stored player.json's would.
 */
export function loadSampleLecture(): PlayerLecture {
  if (!isPlayerJson(fixture)) throw new Error('The sample player.json does not match the schema.')
  return fromPlayerJson(fixture, '/samples/lecture-01/player.json')
}
