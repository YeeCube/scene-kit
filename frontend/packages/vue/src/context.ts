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
  setTag(refs: readonly EntityRef[], field: string, values: unknown): Promise<CommandResult>;
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
