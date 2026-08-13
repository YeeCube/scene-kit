import type { EntityBatch, EntityRef, WorldSnapshot } from './types';

export function entityRefKey(ref: EntityRef): string {
  return `${encodeURIComponent(ref.kind)}:${ref.uid}`;
}

export function selectEntityBatch(snapshot: WorldSnapshot | null | undefined, kind: string): EntityBatch | undefined {
  return snapshot?.entityBatches[kind];
}

export function selectEntityIndex(snapshot: WorldSnapshot | null | undefined, ref: EntityRef): number {
  const uids = snapshot?.entityBatches[ref.kind]?.columns.uid;
  return uids ? uids.indexOf(ref.uid) : -1;
}

/** Materialize one row for an inspector; renderers should continue to consume columns directly. */
export function selectEntity(snapshot: WorldSnapshot | null | undefined, ref: EntityRef): Readonly<Record<string, unknown>> | undefined {
  const batch = selectEntityBatch(snapshot, ref.kind);
  if (!batch) return undefined;
  const index = batch.columns.uid.indexOf(ref.uid);
  if (index < 0) return undefined;
  return Object.fromEntries(Object.entries(batch.columns).map(([name, values]) => [name, values[index]]));
}

export function selectBatches(
  snapshot: WorldSnapshot | null | undefined,
  predicate: (batch: EntityBatch) => boolean,
): readonly EntityBatch[] {
  return snapshot ? Object.values(snapshot.entityBatches).filter(predicate) : [];
}
