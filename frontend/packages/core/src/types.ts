export const SNAPSHOT_PROTOCOL = 'wmk.world-snapshot' as const;
export const DELTA_PROTOCOL = 'wmk.world-delta' as const;
export const PROTOCOL_VERSION = '1.0' as const;

export type EntityUid = string;

export type EntityRef = Readonly<{
  kind: string;
  uid: EntityUid;
}>;

export type ColumnValue = unknown;
export type Column = readonly ColumnValue[];

export type ColumnSchema = Readonly<{
  dtype: string;
  shape?: readonly number[];
  semantic?: string;
  encoding?: string;
  nullable?: boolean;
}>;

export type EntityBatch = Readonly<{
  kind: string;
  geometry: string;
  dim: number;
  role: string;
  parentKind: string | null;
  count: number;
  schema: Readonly<Record<string, ColumnSchema>>;
  columns: Readonly<Record<string, Column>>;
}>;

export type RelationBatch = Readonly<{
  name: string;
  count: number;
  schema: Readonly<Record<string, ColumnSchema>>;
  columns: Readonly<Record<string, Column>>;
}>;

export type WorldMetadata = Readonly<{
  dimensions: number | null;
  coordinateSystem: string;
  bounds: Readonly<Record<string, readonly number[]>>;
  boundary?: Readonly<Record<string, string>>;
}>;

export type WorldSnapshot = Readonly<{
  protocol: typeof SNAPSHOT_PROTOCOL;
  protocolVersion: typeof PROTOCOL_VERSION;
  snapshotId: string;
  tick: number;
  time: number;
  world: WorldMetadata;
  entityBatches: Readonly<Record<string, EntityBatch>>;
  relationBatches: Readonly<Record<string, RelationBatch>>;
  metrics: Readonly<Record<string, number>>;
}>;

export type EntityBatchChange = Readonly<{
  removedUids: readonly EntityUid[];
  added: EntityBatch | null;
  changed: Readonly<{
    uids: readonly EntityUid[];
    columns: Readonly<Record<string, Column>>;
  }>;
}>;

export type WorldDelta = Readonly<{
  protocol: typeof DELTA_PROTOCOL;
  protocolVersion: typeof PROTOCOL_VERSION;
  baseSnapshotId: string;
  snapshotId: string;
  tick: number;
  time: number;
  world: WorldMetadata;
  entityBatches: Readonly<Record<string, EntityBatchChange>>;
  relationBatches: Readonly<Record<string, unknown>>;
  metrics: Readonly<Record<string, number>>;
}>;

export type SnapshotProjection = Readonly<{
  kinds?: readonly string[];
  columns?: readonly string[] | Readonly<Record<string, readonly string[]>>;
  viewport?: Readonly<Record<string, number>>;
  includeRelations?: boolean;
  includeMetrics?: boolean;
  includeWorldCoordinates?: boolean;
}>;

export type WorldCommand = Readonly<{
  type: string;
  commandId?: string;
  payload?: Readonly<Record<string, unknown>>;
}>;

export type CommandResult = Readonly<{
  commandId: string;
  accepted: boolean;
  appliedTick: number;
  error: string | null;
  data: Readonly<Record<string, unknown>>;
}>;

export type SessionDescription = Readonly<{
  name: string;
  tick: number;
  playing: boolean;
  rate: number;
  parameters: Readonly<Record<string, unknown>>;
  capabilities: Readonly<{
    commands: readonly string[];
    snapshot: boolean;
    delta: boolean;
    seek: boolean;
    reset: boolean;
  }>;
}>;

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

export type BridgeEvent =
  | Readonly<{type: 'connection'; state: ConnectionState}>
  | Readonly<{type: 'hello'; description: SessionDescription}>
  | Readonly<{type: 'snapshot'; snapshot: WorldSnapshot}>
  | Readonly<{type: 'commandResult'; result: CommandResult}>
  | Readonly<{type: 'error'; error: Error}>;

export type BridgeListener = (event: BridgeEvent) => void;

export interface WorldModelBridge {
  connect(): Promise<void>;
  disconnect(): void;
  subscribe(listener: BridgeListener): () => void;
  requestSnapshot(): void;
  sendCommand(command: WorldCommand): Promise<CommandResult>;
}
