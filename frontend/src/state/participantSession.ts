import { ref } from 'vue'
import { ApiError } from '../api/client'
import {
  getParticipantProfile,
  type ParticipantProfile,
} from '../api/participantIdentity'

export const participantSession = ref<ParticipantProfile | null>(null)

let refreshGeneration = 0

export function setParticipantSession(profile: ParticipantProfile | null) {
  refreshGeneration += 1
  participantSession.value = profile
}

export async function refreshParticipantSession() {
  const generation = ++refreshGeneration
  try {
    const profile = await getParticipantProfile()
    if (generation === refreshGeneration) participantSession.value = profile
  } catch (error) {
    if (generation !== refreshGeneration) return
    if (error instanceof ApiError && error.statusCode === 401) {
      participantSession.value = null
    }
  }
}
