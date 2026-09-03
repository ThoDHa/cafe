import type { Order } from "../../../api/client";

export type PermissionState = "granted" | "denied" | "default" | "unsupported";

export interface NotificationGate {
  permission(): PermissionState;
  requestPermission(): Promise<PermissionState>;
  show(title: string, body: string): void;
}

export interface AudioPort {
  chime(): void;
}

export interface AlertPorts {
  hidden(): boolean;
  notification: NotificationGate;
  audio: AudioPort;
  muted(): boolean;
}

const MUTE_KEY = "cafe:barista-mute";

export function isMuted(storage: Storage | undefined): boolean {
  return storage?.getItem(MUTE_KEY) === "1";
}

export function setMuted(
  storage: Storage | undefined,
  muted: boolean,
): void {
  if (muted) {
    storage?.setItem(MUTE_KEY, "1");
  } else {
    storage?.removeItem(MUTE_KEY);
  }
}

export interface NewOrderAlert {
  onNewOrder(order: Order): void;
}

export function createNewOrderAlert(ports: AlertPorts): NewOrderAlert {
  return {
    onNewOrder(order) {
      if (!ports.muted()) {
        ports.audio.chime();
      }
      if (
        ports.hidden() &&
        ports.notification.permission() === "granted"
      ) {
        const count = order.items.reduce(
          (total, line) => total + line.quantity,
          0,
        );
        const names = order.items
          .map((line) => `${line.quantity}× ${line.itemNameVi}`)
          .join(", ");
        ports.notification.show(
          `New order ${order.orderNumber}`,
          `${count} drink${count === 1 ? "" : "s"}: ${names}`,
        );
      }
    },
  };
}

export function createOscillatorChime(): AudioPort {
  let context: AudioContext | undefined;
  return {
    chime() {
      if (typeof globalThis.AudioContext !== "function") {
        return;
      }
      context ??= new AudioContext();
      if (context.state === "suspended") {
        void context.resume();
      }
      const now = context.currentTime;
      for (const [offset, frequency] of [
        [0, 880],
        [0.18, 1174.66],
      ] as const) {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.frequency.value = frequency;
        oscillator.type = "sine";
        gain.gain.setValueAtTime(0.0001, now + offset);
        gain.gain.exponentialRampToValueAtTime(0.2, now + offset + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.35);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start(now + offset);
        oscillator.stop(now + offset + 0.4);
      }
    },
  };
}
