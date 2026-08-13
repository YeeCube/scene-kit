import {
  PROTOCOL_VERSION,
  SNAPSHOT_PROTOCOL,
  type Column,
  type EntityBatch,
  type EntityBatchChange,
  type WorldDelta,
  type WorldSnapshot,
} from './types';
import { ProtocolValidationError, validateDelta, validateSnapshot } from './validation';

function applyBatchChange(previous: EntityBatch | undefined, change: EntityBatchChange, kind: string): EntityBatch | undefined {
  if (!previous) {
    if (!change.added) return undefined;
    return change.added;
  }

  const removed = new Set(change.removedUids);
  const previousUids = previous.columns.uid as readonly string[];
  const retainedIndices = previousUids.flatMap((uid, index) => removed.has(uid) ? [] : [index]);
  const mutableColumns: Record<string, unknown[]> = {};
  for (const [name, column] of Object.entries(previous.columns)) {
    mutableColumns[name] = retainedIndices.map((index) => column[index]);
  }

  if (change.added) {
    const names = new Set([...Object.keys(mutableColumns), ...Object.keys(change.added.columns)]);
    for (const name of names) {
      const target = mutableColumns[name] ?? Array(retainedIndices.length).fill(null);
      const source = change.added.columns[name] ?? Array(change.added.count).fill(null);
      target.push(...source);
      mutableColumns[name] = target;
    }
  }

  const uidIndex = new Map((mutableColumns.uid ?? []).map((uid, index) => [String(uid), index]));
  change.changed.uids.forEach((uid, changedIndex) => {
    const row = uidIndex.get(uid);
    if (row === undefined) return;
    for (const [name, column] of Object.entries(change.changed.columns)) {
      if (mutableColumns[name]) mutableColumns[name][row] = column[changedIndex];
    }
  });

  const count = mutableColumns.uid?.length ?? 0;
  if (count === 0 && change.added === null && removed.size === previous.count) return undefined;
  return {
    ...previous,
    ...(change.added ? {
      geometry: change.added.geometry,
      dim: change.added.dim,
      role: change.added.role,
      parentKind: change.added.parentKind,
      schema: {...previous.schema, ...change.added.schema},
    } : {}),
    kind,
    count,
    columns: mutableColumns as Record<string, Column>,
  };
}

export function applyWorldDelta(previous: WorldSnapshot, delta: WorldDelta): WorldSnapshot {
  validateSnapshot(previous);
  validateDelta(delta);
  if (delta.baseSnapshotId !== previous.snapshotId) {
    throw new ProtocolValidationError(`delta base '${delta.baseSnapshotId}' does not match '${previous.snapshotId}'; request a full snapshot`);
  }
  const batches: Record<string, EntityBatch> = {...previous.entityBatches};
  for (const [kind, change] of Object.entries(delta.entityBatches)) {
    const next = applyBatchChange(batches[kind], change, kind);
    if (next) batches[kind] = next;
    else delete batches[kind];
  }
  const snapshot: WorldSnapshot = {
    protocol: SNAPSHOT_PROTOCOL,
    protocolVersion: PROTOCOL_VERSION,
    snapshotId: delta.snapshotId,
    tick: delta.tick,
    time: delta.time,
    world: delta.world,
    entityBatches: batches,
    relationBatches: previous.relationBatches,
    metrics: delta.metrics,
  };
  validateSnapshot(snapshot);
  return snapshot;
}
