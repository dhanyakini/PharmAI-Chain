/** US customary display helpers (backend still uses km / km/h). */

export const KM_TO_MI = 0.621371192;

export function kmToMiles(km: number): number {
  return km * KM_TO_MI;
}

/** km/h → mph (same factor as km → mi). */
export function kmhToMph(kmh: number): number {
  return kmh * KM_TO_MI;
}
