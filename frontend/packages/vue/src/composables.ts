import {selectEntity, selectEntityIndex, type EntityRef} from '@scene-kit/core';
import {computed, inject, type ComputedRef} from 'vue';
import {WorldModelContextKey, type EntityView, type WorldModelContext} from './context';

export function useWorldModel(): WorldModelContext {
  const context = inject(WorldModelContextKey);
  if (!context) throw new Error('useWorldModel() must be used inside <WorldModelProvider>');
  return context;
}

export function useEntityBatch(kind: string) {
  const {snapshot} = useWorldModel();
  return computed(() => snapshot.value?.entityBatches[kind]);
}

export function useEntity(ref: ComputedRef<EntityRef | null> | EntityRef): ComputedRef<EntityView | undefined> {
  const {snapshot} = useWorldModel();
  return computed(() => {
    const current = 'value' in ref ? ref.value : ref;
    if (!current || !snapshot.value) return undefined;
    const batch = snapshot.value.entityBatches[current.kind];
    const values = selectEntity(snapshot.value, current);
    const index = selectEntityIndex(snapshot.value, current);
    return batch && values && index >= 0 ? {ref: current, batch, index, values} : undefined;
  });
}

export function useMetrics() {
  const {snapshot} = useWorldModel();
  return computed(() => snapshot.value?.metrics ?? {});
}
