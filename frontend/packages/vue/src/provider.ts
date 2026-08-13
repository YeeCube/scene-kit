import type {BridgeEvent, EntityRef, WorldModelBridge} from '@scene-kit/core';
import {computed, defineComponent, h, onBeforeUnmount, onMounted, provide, ref, shallowRef, type PropType} from 'vue';
import {WorldModelContextKey, type WorldModelCommands, type WorldModelContext} from './context';

const groupRefs = (refs: readonly EntityRef[]): Map<string, string[]> => {
  const grouped = new Map<string, string[]>();
  for (const ref of refs) grouped.set(ref.kind, [...(grouped.get(ref.kind) ?? []), ref.uid]);
  return grouped;
};

export const WorldModelProvider = defineComponent({
  name: 'WorldModelProvider',
  props: {
    bridge: {type: Object as PropType<WorldModelBridge>, required: true},
    autoConnect: {type: Boolean, default: true},
  },
  setup(props, {slots}) {
    const connection = ref<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
    const snapshot = shallowRef<WorldModelContext['snapshot']['value']>(null);
    const description = shallowRef<WorldModelContext['description']['value']>(null);
    const errors = ref<readonly string[]>([]);

    const dispatch = (type: string, payload: Readonly<Record<string, unknown>> = {}) =>
      props.bridge.sendCommand({type, payload});

    const commands: WorldModelCommands = {
      play: () => dispatch('play'),
      pause: () => dispatch('pause'),
      step: (steps = 1) => dispatch('step', {steps}),
      reset: () => dispatch('reset'),
      setRate: (rate) => dispatch('set_rate', {rate}),
      setParameter: (name, value) => dispatch('set_parameter', {name, value}),
      spawn: (kind, count, attributes = {}) => dispatch('spawn', {kind, n: count, attributes}),
      async despawn(refs) {
        const results = await Promise.all([...groupRefs(refs)].map(([kind, uids]) => dispatch('despawn', {kind, uids})));
        return results.at(-1)!;
      },
      async move(refs, delta) {
        const results = await Promise.all([...groupRefs(refs)].map(([kind, uids]) => dispatch('move', {kind, uids, delta})));
        return results.at(-1)!;
      },
      async setTag(refs, field, values) {
        const results = await Promise.all([...groupRefs(refs)].map(([kind, uids]) => dispatch('set_tag', {kind, uids, field, values})));
        return results.at(-1)!;
      },
    };

    const onEvent = (event: BridgeEvent) => {
      if (event.type === 'connection') connection.value = event.state;
      else if (event.type === 'snapshot') snapshot.value = event.snapshot;
      else if (event.type === 'hello') description.value = event.description;
      else if (event.type === 'error') errors.value = [...errors.value, event.error.message];
      else if (event.type === 'commandResult' && !event.result.accepted) {
        errors.value = [...errors.value, event.result.error ?? `Command ${event.result.commandId} was rejected`];
      }
    };

    const unsubscribe = props.bridge.subscribe(onEvent);
    provide(WorldModelContextKey, {
      bridge: props.bridge,
      connection,
      snapshot,
      description,
      errors,
      tick: computed(() => snapshot.value?.tick ?? description.value?.tick ?? 0),
      commands,
      clearErrors: () => { errors.value = []; },
    });

    onMounted(() => {
      if (props.autoConnect) void props.bridge.connect().catch(() => undefined);
    });
    onBeforeUnmount(() => {
      unsubscribe();
      props.bridge.disconnect();
    });
    return () => h('div', {class: 'wmk-provider'}, slots.default?.());
  },
});
