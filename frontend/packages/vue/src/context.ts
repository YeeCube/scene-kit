import type {
  CommandResult,
  ConnectionState,
  EntityBatch,
  EntityRef,
  SessionDescription,
  WorldModelBridge,
  WorldSnapshot,
} from '@scene-kit/core';
import type {ComputedRef, InjectionKey, Ref, ShallowRef} from 'vue';

export type SelectionRect = Readonly<{u_min?: number; u_max?: number; v_min?: number; v_max?: number}>;

export type SnapResult = Readonly<{
  snapped: ReadonlyArray<Readonly<{uid: string; slotUid: string}>>;
  skipped: readonly string[];
}>;

export type WorldModelCommands = Readonly<{
  play(): Promise<CommandResult>;
  pause(): Promise<CommandResult>;
  step(steps?: number): Promise<CommandResult>;
  reset(): Promise<CommandResult>;
  setRate(rate: number): Promise<CommandResult>;
  setParameter(name: string, value: unknown): Promise<CommandResult>;
  spawn(kind: string, count: number, attributes?: Readonly<Record<string, unknown>>): Promise<CommandResult>;
  despawn(refs: readonly EntityRef[]): Promise<CommandResult>;
  move(refs: readonly EntityRef[], delta: readonly number[] | readonly (readonly number[])[]): Promise<CommandResult>;
  setAttribute(refs: readonly EntityRef[], field: string, values: unknown): Promise<CommandResult>;
  setTag(refs: readonly EntityRef[], field: string, values: unknown): Promise<CommandResult>;
  select(kind: string, target: Readonly<{uids?: readonly string[]; rect?: SelectionRect; mode?: 'replace' | 'add' | 'remove'}>): Promise<CommandResult>;
  clearSelection(): Promise<CommandResult>;
  getSelection(): Promise<CommandResult>;
  batchMove(delta: readonly number[], kinds?: readonly string[]): Promise<CommandResult>;
  batchSetAttribute(field: string, value: unknown, kinds?: readonly string[]): Promise<CommandResult>;
  bindRelation(name: string, srcKind: string, dstKind: string, srcUids: readonly string[], dstUids: readonly string[], attrs?: Readonly<Record<string, unknown>>): Promise<CommandResult>;
  unbindRelation(name: string, endpoints?: Readonly<{srcUids?: readonly string[]; dstUids?: readonly string[]}>): Promise<CommandResult>;
  snapToSlots(kind: string, slotKind: string, options?: Readonly<{radius?: number; relation?: string; align?: boolean; uids?: readonly string[]}>): Promise<CommandResult>;
}>;

export type WorldModelContext = Readonly<{
  bridge: WorldModelBridge;
  connection: Ref<ConnectionState>;
  snapshot: ShallowRef<WorldSnapshot | null>;
  description: ShallowRef<SessionDescription | null>;
  errors: Ref<readonly string[]>;
  tick: ComputedRef<number>;
  commands: WorldModelCommands;
  clearErrors(): void;
}>;

export const WorldModelContextKey: InjectionKey<WorldModelContext> = Symbol('WorldModelContext');

export type EntityView = Readonly<{ref: EntityRef; batch: EntityBatch; index: number; values: Readonly<Record<string, unknown>>}>;
