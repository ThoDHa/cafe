import type { Order } from "../../../api/client";

export type PermissionState = "granted" | "denied" | "default" | "unsupported";

export interface NotificationWindow {
  permission(): PermissionState;
  requestPermission(): Promise<PermissionState>;
  show(title: string, body: string): void;
}

export function browserNotificationWindow(): NotificationWindow | null {
  if (typeof globalThis.Notification !== "function") {
    return null;
  }
  return {
    permission: () => globalThis.Notification.permission as PermissionState,
    requestPermission: async () =>
      (await globalThis.Notification.requestPermission()) as PermissionState,
    show(title, body) {
      new globalThis.Notification(title, { body });
    },
  };
}

export interface ReadyNotifier {
  readonly permission: PermissionState;
  readonly optedIn: boolean;
  optIn(): Promise<boolean>;
  onOrderStatus(order: Order): void;
}

export function createReadyNotifier(
  window: NotificationWindow,
): ReadyNotifier {
  let optedIn = false;
  const notified = new Set<string>();
  const state = {
    get permission(): PermissionState {
      return window.permission();
    },
    get optedIn(): boolean {
      return optedIn;
    },
    async optIn(): Promise<boolean> {
      const outcome = await window.requestPermission();
      optedIn = outcome === "granted";
      return optedIn;
    },
    onOrderStatus(order: Order): void {
      if (
        !optedIn ||
        window.permission() !== "granted" ||
        order.status !== "completed" ||
        notified.has(order.id)
      ) {
        return;
      }
      notified.add(order.id);
      const name =
        order.customerName && order.customerName.length > 0
          ? ` for ${order.customerName}`
          : "";
      window.show(
        `Order ${order.orderNumber} is ready`,
        `Your drink${name} is ready to pick up.`,
      );
    },
  };
  return state;
}
