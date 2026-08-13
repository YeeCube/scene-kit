import { applyWorldDelta } from './delta';
import type {
  BridgeEvent,
  BridgeListener,
  CommandResult,
  SessionDescription,
  WorldCommand,
  WorldModelBridge,
  WorldSnapshot,
} from './types';
import { validateDelta, validateSnapshot } from './validation';

const commandId = (): string =>
  globalThis.crypto?.randomUUID?.() ?? `command-${Date.now()}-${Math.random().toString(16).slice(2)}`;

abstract class BaseBridge {
  protected readonly listeners = new Set<BridgeListener>();

  subscribe(listener: BridgeListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  protected emit(event: BridgeEvent): void {
    for (const listener of this.listeners) listener(event);
  }
}

type ServerEnvelope = {type: string; payload: unknown};

export class WebSocketBridge extends BaseBridge implements WorldModelBridge {
  private socket?: WebSocket;
  private snapshot?: WorldSnapshot;
  private readonly pending = new Map<string, {resolve: (value: CommandResult) => void; reject: (reason: unknown) => void}>();

  constructor(readonly url: string, private readonly protocols?: string | string[]) {
    super();
  }

  connect(): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve();
    this.emit({type: 'connection', state: 'connecting'});
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(this.url, this.protocols);
      this.socket = socket;
      socket.addEventListener('open', () => {
        this.emit({type: 'connection', state: 'connected'});
        resolve();
      }, {once: true});
      socket.addEventListener('error', () => {
        const error = new Error(`Unable to connect to ${this.url}`);
        this.emit({type: 'connection', state: 'error'});
        this.emit({type: 'error', error});
        reject(error);
      }, {once: true});
      socket.addEventListener('message', (event) => this.receive(String(event.data)));
      socket.addEventListener('close', () => {
        this.emit({type: 'connection', state: 'disconnected'});
        for (const request of this.pending.values()) request.reject(new Error('WebSocket disconnected'));
        this.pending.clear();
      });
    });
  }

  disconnect(): void {
    this.socket?.close();
    this.socket = undefined;
  }

  requestSnapshot(): void {
    this.send({type: 'getSnapshot'});
  }

  sendCommand(command: WorldCommand): Promise<CommandResult> {
    const normalized = {...command, commandId: command.commandId ?? commandId()};
    return new Promise((resolve, reject) => {
      this.pending.set(normalized.commandId, {resolve, reject});
      try {
        this.send({type: 'command', payload: normalized});
      } catch (error) {
        this.pending.delete(normalized.commandId);
        reject(error);
      }
    });
  }

  private send(value: unknown): void {
    if (this.socket?.readyState !== WebSocket.OPEN) throw new Error('WebSocket is not connected');
    this.socket.send(JSON.stringify(value));
  }

  private receive(raw: string): void {
    try {
      const envelope = JSON.parse(raw) as ServerEnvelope;
      if (envelope.type === 'hello') {
        this.emit({type: 'hello', description: envelope.payload as SessionDescription});
      } else if (envelope.type === 'snapshot') {
        validateSnapshot(envelope.payload);
        this.snapshot = envelope.payload;
        this.emit({type: 'snapshot', snapshot: this.snapshot});
      } else if (envelope.type === 'delta') {
        validateDelta(envelope.payload);
        if (!this.snapshot) {
          this.requestSnapshot();
          return;
        }
        try {
          this.snapshot = applyWorldDelta(this.snapshot, envelope.payload);
          this.emit({type: 'snapshot', snapshot: this.snapshot});
        } catch (error) {
          this.emit({type: 'error', error: error instanceof Error ? error : new Error(String(error))});
          this.requestSnapshot();
        }
      } else if (envelope.type === 'commandResult') {
        const result = envelope.payload as CommandResult;
        this.pending.get(result.commandId)?.resolve(result);
        this.pending.delete(result.commandId);
        this.emit({type: 'commandResult', result});
      } else if (envelope.type === 'error') {
        const payload = envelope.payload as {message?: unknown};
        this.emit({type: 'error', error: new Error(String(payload?.message ?? 'Unknown server error'))});
      }
    } catch (error) {
      this.emit({type: 'error', error: error instanceof Error ? error : new Error(String(error))});
    }
  }
}

export type FixtureCommandHandler = (
  command: Required<Pick<WorldCommand, 'type' | 'commandId'>> & WorldCommand,
  snapshot: WorldSnapshot,
) => WorldSnapshot | Promise<WorldSnapshot>;

export class FixtureBridge extends BaseBridge implements WorldModelBridge {
  constructor(private snapshot: WorldSnapshot, private readonly handler?: FixtureCommandHandler) {
    super();
    validateSnapshot(snapshot);
  }

  async connect(): Promise<void> {
    this.emit({type: 'connection', state: 'connected'});
    this.emit({type: 'snapshot', snapshot: this.snapshot});
  }

  disconnect(): void {
    this.emit({type: 'connection', state: 'disconnected'});
  }

  requestSnapshot(): void {
    this.emit({type: 'snapshot', snapshot: this.snapshot});
  }

  async sendCommand(command: WorldCommand): Promise<CommandResult> {
    const id = command.commandId ?? commandId();
    try {
      if (this.handler) this.snapshot = await this.handler({...command, commandId: id, type: command.type}, this.snapshot);
      const result: CommandResult = {commandId: id, accepted: true, appliedTick: this.snapshot.tick, error: null, data: {}};
      this.emit({type: 'commandResult', result});
      this.emit({type: 'snapshot', snapshot: this.snapshot});
      return result;
    } catch (error) {
      const result: CommandResult = {commandId: id, accepted: false, appliedTick: this.snapshot.tick, error: String(error), data: {}};
      this.emit({type: 'commandResult', result});
      return result;
    }
  }
}
