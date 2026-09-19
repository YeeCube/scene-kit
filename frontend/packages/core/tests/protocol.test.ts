import {describe, expect, it} from 'vitest';
import {applyWorldDelta, parseSnapshot, selectEntity, type WorldDelta, type WorldSnapshot} from '../src';

const snapshot: WorldSnapshot = {
  protocol: 'scene-kit.world-snapshot', protocolVersion: '1.1', snapshotId: 's1', tick: 1, time: 1,
  world: {dimensions: 2, coordinateSystem: 'root-parametric', bounds: {u: [0, 10], v: [0, 10]}},
  entityBatches: {bird: {kind: 'bird', geometry: 'point', dim: 0, role: 'AGENT', parentKind: null, count: 2,
    schema: {uid: {dtype: 'int64'}, u: {dtype: 'float32'}}, columns: {uid: ['9007199254740993', '8'], u: [1, 2]}}},
  relationBatches: {}, metrics: {},
};

describe('protocol', () => {
  it('validates SoA and preserves string uid', () => {
    expect(parseSnapshot(snapshot).entityBatches.bird.columns.uid[0]).toBe('9007199254740993');
    expect(selectEntity(snapshot, {kind: 'bird', uid: '8'})).toEqual({uid: '8', u: 2});
  });

  it('applies columnar delta', () => {
    const delta: WorldDelta = {protocol: 'scene-kit.world-delta', protocolVersion: '1.1', baseSnapshotId: 's1', snapshotId: 's2', tick: 2, time: 2,
      world: snapshot.world, relationBatches: {}, metrics: {}, entityBatches: {bird: {removedUids: ['9007199254740993'], added: null,
        changed: {uids: ['8'], columns: {u: [7]}}}}};
    const next = applyWorldDelta(snapshot, delta);
    expect(next.entityBatches.bird.columns).toEqual({uid: ['8'], u: [7]});
  });

  it('rejects inconsistent column length', () => {
    expect(() => parseSnapshot({...snapshot, entityBatches: {bird: {...snapshot.entityBatches.bird, count: 3}}})).toThrow(/length/);
  });

  it('applies relation delta (added/removedEdges)', () => {
    const base: WorldSnapshot = {
      ...snapshot,
      relationBatches: {
        is_on: {name: 'is_on', srcKind: 'piece', dstKind: 'slot', count: 1,
          schema: {srcUid: {dtype: 'int64'}, dstUid: {dtype: 'int64'}},
          columns: {srcUid: ['1'], dstUid: ['10']}},
      },
    };
    const delta: WorldDelta = {protocol: 'scene-kit.world-delta', protocolVersion: '1.1', baseSnapshotId: 's1', snapshotId: 's3', tick: 3, time: 3,
      world: snapshot.world, entityBatches: {}, metrics: {},
      relationBatches: {is_on: {
        removedEdges: [['1', '10']],
        added: {name: 'is_on', srcKind: 'piece', dstKind: 'slot', count: 2,
          schema: {srcUid: {dtype: 'int64'}, dstUid: {dtype: 'int64'}},
          columns: {srcUid: ['2', '3'], dstUid: ['11', '12']}},
        changed: {edges: [], columns: {}},
      }},
    };
    const next = applyWorldDelta(base, delta as WorldDelta);
    expect(next.relationBatches.is_on.count).toBe(2);
    expect(next.relationBatches.is_on.columns.srcUid).toEqual(['2', '3']);
    expect(next.relationBatches.is_on.columns.dstUid).toEqual(['11', '12']);
  });
});
