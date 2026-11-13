const ACTIVE_ATHLETE_KEY = 'apex.activeAthleteId';
const TRACKED_JOBS_KEY = 'apex.trackedJobs';

export function loadActiveAthleteId(): string {
  return localStorage.getItem(ACTIVE_ATHLETE_KEY) || '';
}

export function saveActiveAthleteId(athleteId: string): void {
  if (athleteId) localStorage.setItem(ACTIVE_ATHLETE_KEY, athleteId);
  else localStorage.removeItem(ACTIVE_ATHLETE_KEY);
}

export function loadTrackedJobIds(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(TRACKED_JOBS_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
  } catch {
    return [];
  }
}

export function saveTrackedJobIds(ids: string[]): void {
  localStorage.setItem(TRACKED_JOBS_KEY, JSON.stringify([...new Set(ids)]));
}
