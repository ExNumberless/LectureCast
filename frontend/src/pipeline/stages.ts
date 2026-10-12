import type { components } from '../api/schema'

export type StageNode = components['schemas']['StageNode']
export type StageName = StageNode['stage']
export type NodeStatus = StageNode['status']
export type Lecture = components['schemas']['Lecture']
export type Course = components['schemas']['Course']

export const LECTURE_STAGES: StageName[] = ['materials', 'transcript', 'tts', 'render', 'assemble']

export const STAGE_LABELS: Record<StageName, string> = {
  fetch: 'Fetch',
  upload: 'Import',
  review: 'Review',
  materials: 'Materials',
  transcript: 'Transcript',
  tts: 'Narration',
  render: 'Slides',
  assemble: 'Slideshow',
}

export const STATUS_LABELS: Record<NodeStatus, string> = {
  pending: 'Not started',
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Done',
  failed: 'Failed',
  stale: 'Stale',
}

export function sourceStage(course: Pick<Course, 'provider'>): StageName {
  return course.provider === 'website' ? 'fetch' : 'upload'
}

/** Course-level stages first, then one column per lecture stage. */
export function stageColumns(course: Pick<Course, 'provider'>): StageName[] {
  return [sourceStage(course), 'review', ...LECTURE_STAGES]
}

export function isCourseStage(stage: StageName) {
  return !LECTURE_STAGES.includes(stage)
}

export function nodeKey(stage: StageName, lectureId: number | null) {
  return `${stage}:${lectureId ?? 'course'}`
}

export function indexNodes(nodes: StageNode[]) {
  return new Map(nodes.map((node) => [nodeKey(node.stage, node.lecture), node]))
}

export function isActive(status: NodeStatus | undefined) {
  return status === 'queued' || status === 'running'
}

export type Progress = { name?: string; done?: number; total?: number }

export function progressText(node: StageNode | undefined) {
  const progress = node?.latest_run?.progress as Progress | undefined
  if (node?.status !== 'running' || !progress?.total) return null
  return `${progress.done ?? 0}/${progress.total}`
}
