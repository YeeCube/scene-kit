import type {EntityBatch, EntityRef, WorldSnapshot} from '@scene-kit/core';
import {applyCameraToCanvas2D, type Camera2D} from 'viewport-2d-kit/core';

export type PointStyle = Readonly<{fill?: string; radius?: number; alpha?: number}>;
export type PointStyleMap = Readonly<Record<string, PointStyle>>;

const numberAt = (batch: EntityBatch, name: string, index: number, fallback: number): number => {
  const value = batch.columns[name]?.[index];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
};

const positionColumns = (batch: EntityBatch): readonly [readonly unknown[], readonly unknown[]] | undefined => {
  const x = batch.columns.world_x ?? batch.columns.u;
  const y = batch.columns.world_y ?? batch.columns.v;
  return x && y ? [x, y] : undefined;
};

const rgbaAt = (batch: EntityBatch, index: number, style: PointStyle): string => {
  if (style.fill) return style.fill;
  const r = numberAt(batch, 'r', index, 70);
  const g = numberAt(batch, 'g', index, 160);
  const b = numberAt(batch, 'b', index, 230);
  const alpha = style.alpha ?? numberAt(batch, 'a', index, 255) / 255;
  return `rgba(${r},${g},${b},${alpha})`;
};

export function drawPointBatches(
  ctx: CanvasRenderingContext2D,
  snapshot: WorldSnapshot,
  camera: Camera2D,
  viewport: {width: number; height: number; dpr?: number},
  styles: PointStyleMap = {},
  selected: EntityRef | null = null,
  kinds?: readonly string[],
): void {
  const dpr = viewport.dpr ?? 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, viewport.width * dpr, viewport.height * dpr);
  applyCameraToCanvas2D(ctx, {
    scale: camera.scale * dpr,
    pan: {x: camera.pan.x * dpr, y: camera.pan.y * dpr},
  });
  for (const batch of Object.values(snapshot.entityBatches)) {
    if (batch.geometry !== 'point' || (kinds && !kinds.includes(batch.kind))) continue;
    const position = positionColumns(batch);
    if (!position) continue;
    const [xs, ys] = position;
    const style = styles[batch.kind] ?? {};
    for (let index = 0; index < batch.count; index += 1) {
      const x = Number(xs[index]);
      const y = Number(ys[index]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      const radius = style.radius ?? Math.max(1, numberAt(batch, 'size', index, 2.5));
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = rgbaAt(batch, index, style);
      ctx.fill();
      if (selected?.kind === batch.kind && selected.uid === batch.columns.uid[index]) {
        ctx.lineWidth = 2 / Math.max(camera.scale, 0.0001);
        ctx.strokeStyle = '#f8fafc';
        ctx.stroke();
      }
    }
  }
}

export function hitTestPointBatches(
  snapshot: WorldSnapshot,
  point: {x: number; y: number},
  toleranceWorld: number,
  styles: PointStyleMap = {},
  kinds?: readonly string[],
): EntityRef | null {
  let best: {ref: EntityRef; distance2: number} | null = null;
  for (const batch of Object.values(snapshot.entityBatches)) {
    if (batch.geometry !== 'point' || (kinds && !kinds.includes(batch.kind))) continue;
    const position = positionColumns(batch);
    if (!position) continue;
    const [xs, ys] = position;
    for (let index = 0; index < batch.count; index += 1) {
      const dx = Number(xs[index]) - point.x;
      const dy = Number(ys[index]) - point.y;
      const radius = styles[batch.kind]?.radius ?? Math.max(1, numberAt(batch, 'size', index, 2.5));
      const limit = radius + toleranceWorld;
      const distance2 = dx * dx + dy * dy;
      if (distance2 <= limit * limit && (!best || distance2 < best.distance2)) {
        best = {ref: {kind: batch.kind, uid: String(batch.columns.uid[index])}, distance2};
      }
    }
  }
  return best?.ref ?? null;
}
