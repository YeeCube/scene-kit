import {
  DELTA_PROTOCOL,
  PROTOCOL_VERSION,
  SNAPSHOT_PROTOCOL,
  type ColumnSchema,
  type EntityBatch,
  type WorldDelta,
  type WorldSnapshot,
} from './types';

export class ProtocolValidationError extends Error {
  override name = 'ProtocolValidationError';
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

function fail(message: string): never {
  throw new ProtocolValidationError(message);
}

function assertRecord(value: unknown, message: string): asserts value is Record<string, unknown> {
  if (!isRecord(value)) fail(message);
}

const supportedDtype = (dtype: string): boolean =>
  /^(?:u?int(?:8|16|32|64)|float(?:16|32|64)|bool|str|string|object|<[UO]\d*)$/.test(dtype);

function validateSchema(schema: unknown, label: string): asserts schema is Record<string, ColumnSchema> {
  assertRecord(schema, `${label}.schema must be an object`);
  for (const [name, raw] of Object.entries(schema)) {
    assertRecord(raw, `${label}.schema.${name} must be an object`);
    if (typeof raw.dtype !== 'string') fail(`${label}.schema.${name}.dtype must be a string`);
    if (!supportedDtype(raw.dtype)) fail(`${label}.schema.${name} has unsupported dtype '${raw.dtype}'`);
    if (raw.shape !== undefined && (!Array.isArray(raw.shape) || raw.shape.some((item) => !Number.isInteger(item) || item < 0))) {
      fail(`${label}.schema.${name}.shape must contain non-negative integers`);
    }
  }
}

function validateEntityBatch(raw: unknown, label: string): asserts raw is EntityBatch {
  assertRecord(raw, `${label} must be an object`);
  if (typeof raw.kind !== 'string') fail(`${label}.kind must be a string`);
  if (!Number.isInteger(raw.count) || (raw.count as number) < 0) fail(`${label}.count must be a non-negative integer`);
  validateSchema(raw.schema, label);
  assertRecord(raw.columns, `${label}.columns must be an object`);
  const count = raw.count as number;
  for (const [name, column] of Object.entries(raw.columns)) {
    if (!Array.isArray(column)) fail(`${label}.columns.${name} must be an array`);
    if (column.length !== count) fail(`${label}.columns.${name} length ${column.length} does not match count ${count}`);
    if (!(name in raw.schema)) fail(`${label}.columns.${name} has no schema entry`);
  }
  const uids = raw.columns.uid;
  if (!Array.isArray(uids) || uids.some((uid) => typeof uid !== 'string')) fail(`${label}.columns.uid must contain decimal strings`);
  if (new Set(uids).size !== uids.length) fail(`${label}.columns.uid contains duplicate values`);
}

export function validateSnapshot(value: unknown): asserts value is WorldSnapshot {
  assertRecord(value, 'snapshot must be an object');
  if (value.protocol !== SNAPSHOT_PROTOCOL) fail(`unknown snapshot protocol '${String(value.protocol)}'`);
  if (value.protocolVersion !== PROTOCOL_VERSION) fail(`unsupported protocolVersion '${String(value.protocolVersion)}'`);
  if (typeof value.snapshotId !== 'string') fail('snapshotId must be a string');
  if (!Number.isInteger(value.tick)) fail('tick must be an integer');
  assertRecord(value.entityBatches, 'entityBatches must be an object');
  for (const [kind, batch] of Object.entries(value.entityBatches)) validateEntityBatch(batch, `entityBatches.${kind}`);
  assertRecord(value.relationBatches, 'relationBatches must be an object');
  assertRecord(value.metrics, 'metrics must be an object');
}

export function parseSnapshot(value: unknown): WorldSnapshot {
  validateSnapshot(value);
  return value;
}

export function validateDelta(value: unknown): asserts value is WorldDelta {
  assertRecord(value, 'delta must be an object');
  if (value.protocol !== DELTA_PROTOCOL) fail(`unknown delta protocol '${String(value.protocol)}'`);
  if (value.protocolVersion !== PROTOCOL_VERSION) fail(`unsupported protocolVersion '${String(value.protocolVersion)}'`);
  if (typeof value.baseSnapshotId !== 'string' || typeof value.snapshotId !== 'string') fail('delta snapshot ids must be strings');
  if (!Number.isInteger(value.tick)) fail('delta tick must be an integer');
  assertRecord(value.entityBatches, 'delta.entityBatches must be an object');
  for (const [kind, change] of Object.entries(value.entityBatches)) {
    assertRecord(change, `delta.entityBatches.${kind} must be an object`);
    if (!Array.isArray(change.removedUids) || change.removedUids.some((uid) => typeof uid !== 'string')) {
      fail(`delta.entityBatches.${kind}.removedUids must contain strings`);
    }
    if (change.added !== null && change.added !== undefined) validateEntityBatch(change.added, `delta.entityBatches.${kind}.added`);
    assertRecord(change.changed, `delta.entityBatches.${kind}.changed must be an object`);
    if (!Array.isArray(change.changed.uids)) fail(`delta.entityBatches.${kind}.changed.uids must be an array`);
    assertRecord(change.changed.columns, `delta.entityBatches.${kind}.changed.columns must be an object`);
    for (const [name, column] of Object.entries(change.changed.columns)) {
      if (!Array.isArray(column) || column.length !== change.changed.uids.length) {
        fail(`delta.entityBatches.${kind}.changed.columns.${name} has an invalid length`);
      }
    }
  }
}
