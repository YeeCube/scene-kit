import type {EntityRef, WorldSnapshot} from '@scene-kit/core';
import {Viewport2DCanvas, type Viewport2DCanvasExpose} from 'viewport-2d-kit/vue';
import {defineComponent, h, nextTick, onBeforeUnmount, ref, watch, type PropType} from 'vue';
import {drawPointBatches, hitTestPointBatches, type PointStyleMap} from './render';

export const WorldViewport2D = defineComponent({
  name: 'WorldViewport2D',
  props: {
    snapshot: {type: Object as PropType<WorldSnapshot | null>, default: null},
    selected: {type: Object as PropType<EntityRef | null>, default: null},
    kinds: {type: Array as PropType<readonly string[]>, default: undefined},
    styles: {type: Object as PropType<PointStyleMap>, default: () => ({})},
  },
  emits: {
    select: (_value: EntityRef | null) => true,
    move: (_ref: EntityRef, _delta: {x: number; y: number}) => true,
    cameraChange: (_value: unknown) => true,
  },
  setup(props, {emit, expose}) {
    const viewport = ref<Viewport2DCanvasExpose>();
    const canvas = ref<HTMLCanvasElement>();
    let camera = {scale: 1, pan: {x: 0, y: 0}};
    let size = {width: 1, height: 1};
    let animationFrame = 0;
    let drag: {ref: EntityRef; start: {x: number; y: number}; last: {x: number; y: number}} | undefined;

    const bounds = () => {
      const worldBounds = props.snapshot?.world.bounds;
      const u = worldBounds?.u ?? worldBounds?.x ?? [0, 100];
      const v = worldBounds?.v ?? worldBounds?.y ?? [0, 100];
      return {x: Number(u[0]), y: Number(v[0]), width: Number(u[1]) - Number(u[0]), height: Number(v[1]) - Number(v[0])};
    };

    const draw = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(() => {
        const element = canvas.value;
        if (!element || !props.snapshot) return;
        const dpr = window.devicePixelRatio || 1;
        const width = Math.max(1, Math.round(size.width * dpr));
        const height = Math.max(1, Math.round(size.height * dpr));
        if (element.width !== width) element.width = width;
        if (element.height !== height) element.height = height;
        const context = element.getContext('2d');
        if (context) drawPointBatches(context, props.snapshot, camera, {...size, dpr}, props.styles, props.selected, props.kinds);
      });
    };

    const onCameraChange = (nextCamera: typeof camera, nextSize: typeof size) => {
      camera = nextCamera;
      size = nextSize;
      emit('cameraChange', nextCamera);
      draw();
    };

    const onClick = (event: MouseEvent) => {
      if (drag) return;
      if (!props.snapshot || !viewport.value) return;
      const rect = (event.currentTarget as HTMLCanvasElement).getBoundingClientRect();
      const worldPoint = viewport.value.screenToWorld({x: event.clientX - rect.left, y: event.clientY - rect.top});
      emit('select', hitTestPointBatches(props.snapshot, worldPoint, 5 / Math.max(camera.scale, 0.001), props.styles, props.kinds));
    };

    const worldPoint = (event: PointerEvent) => {
      const rect = (event.currentTarget as HTMLCanvasElement).getBoundingClientRect();
      return viewport.value!.screenToWorld({x: event.clientX - rect.left, y: event.clientY - rect.top});
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!props.snapshot || !viewport.value || event.button !== 0) return;
      const point = worldPoint(event);
      const hit = hitTestPointBatches(props.snapshot, point, 5 / Math.max(camera.scale, 0.001), props.styles, props.kinds);
      if (!hit) return;
      drag = {ref: hit, start: point, last: point};
      (event.currentTarget as HTMLCanvasElement).setPointerCapture(event.pointerId);
      emit('select', hit);
    };
    const onPointerMove = (event: PointerEvent) => {
      if (!drag || !viewport.value) return;
      drag.last = worldPoint(event);
    };
    const onPointerUp = (event: PointerEvent) => {
      if (!drag) return;
      const current = drag;
      drag = undefined;
      const delta = {x: current.last.x - current.start.x, y: current.last.y - current.start.y};
      if (Math.abs(delta.x) > 0.001 || Math.abs(delta.y) > 0.001) emit('move', current.ref, delta);
    };

    expose({exportPng: () => canvas.value?.toDataURL('image/png')});

    watch(() => [props.snapshot, props.selected, props.styles, props.kinds], () => void nextTick(draw), {deep: false});
    onBeforeUnmount(() => cancelAnimationFrame(animationFrame));

    return () => h(Viewport2DCanvas, {
      ref: viewport,
      viewBox: bounds(),
      minScale: 0.02,
      maxScale: 100,
      class: 'wmk-world-viewport-2d',
      style: {position: 'relative', display: 'block', width: '100%', height: '100%', overflow: 'hidden'},
      onCameraChange,
    }, {
      default: () => h('canvas', {
        ref: canvas,
        class: 'wmk-world-viewport-2d__canvas',
        style: {position: 'absolute', inset: '0', width: '100%', height: '100%', cursor: 'crosshair'},
        onClick,
        onPointerdown: onPointerDown,
        onPointermove: onPointerMove,
        onPointerup: onPointerUp,
      }),
    });
  },
});
