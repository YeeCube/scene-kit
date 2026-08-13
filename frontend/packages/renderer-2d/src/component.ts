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
    cameraChange: (_value: unknown) => true,
  },
  setup(props, {emit}) {
    const viewport = ref<Viewport2DCanvasExpose>();
    const canvas = ref<HTMLCanvasElement>();
    let camera = {scale: 1, pan: {x: 0, y: 0}};
    let size = {width: 1, height: 1};
    let animationFrame = 0;

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
      if (!props.snapshot || !viewport.value) return;
      const rect = (event.currentTarget as HTMLCanvasElement).getBoundingClientRect();
      const worldPoint = viewport.value.screenToWorld({x: event.clientX - rect.left, y: event.clientY - rect.top});
      emit('select', hitTestPointBatches(props.snapshot, worldPoint, 5 / Math.max(camera.scale, 0.001), props.styles, props.kinds));
    };

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
      }),
    });
  },
});
