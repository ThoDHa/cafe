import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react";
import type { ApiClient, Order, ServerEvent } from "../../api/client";
import {
  boardReducer,
  buildTransition,
  type BoardState,
} from "../../state/barista-orders";
import { createDevClient } from "../ordering/lib/devClient";
import {
  createNewOrderAlert,
  createOscillatorChime,
  isMuted,
  setMuted,
  type NotificationGate,
  type PermissionState,
} from "./lib/alert";
import "./barista.css";

const FLASH_MS = 2500;

function unsupportedGate(): NotificationGate {
  return {
    permission: () => "unsupported",
    requestPermission: async () => "unsupported",
    show: () => undefined,
  };
}

function browserGate(): NotificationGate {
  if (typeof globalThis.Notification !== "function") {
    return unsupportedGate();
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

function elapsedOf(iso: string, now: number): string {
  const seconds = Math.max(0, Math.floor((now - Date.parse(iso)) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function BaristaPage({
  client = createDevClient(),
}: {
  client?: ApiClient;
}) {
  const [board, dispatchBoard] = useReducer(boardReducer, {
    active: [],
    done: [],
  } satisfies BoardState);
  const [now, setNow] = useState(() => Date.now());
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set());
  const [muted, setMutedState] = useState(() => isMuted(window.localStorage));
  const [permission, setPermission] = useState(() =>
    browserGate().permission(),
  );

  const alertRef = useRef(
    createNewOrderAlert({
      hidden: () => document.hidden,
      notification: browserGate(),
      audio: createOscillatorChime(),
      muted: () => isMuted(window.localStorage),
    }),
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;

    const handleEvent = (event: ServerEvent) => {
      dispatchBoard({ type: "event", event });
      if (event.type === "order:new") {
        alertRef.current.onNewOrder(event.order);
        setFlashIds((current) => {
          const next = new Set(current);
          next.add(event.order.id);
          return next;
        });
        window.setTimeout(() => {
          setFlashIds((current) => {
            const next = new Set(current);
            next.delete(event.order.id);
            return next;
          });
        }, FLASH_MS);
      }
    };

    client.listActiveOrders().then((orders) => {
      if (cancelled) {
        return;
      }
      dispatchBoard({ type: "snapshot", orders });
      unsubscribe = client.subscribeToEvents(handleEvent);
    });

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [client]);

  useEffect(() => {
    const refresh = () => {
      client.listActiveOrders().then((orders) => {
        dispatchBoard({ type: "snapshot", orders });
      });
    };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [client]);

  const act = useCallback(
    async (order: Order, action: "start" | "complete" | "cancel") => {
      const transition = buildTransition(order, action);
      if (transition === null) {
        return;
      }
      await client.transitionStatus(transition.orderId, transition.status);
    },
    [client],
  );

  const newOrders = board.active.filter((order) => order.status === "placed");
  const making = board.active.filter(
    (order) => order.status === "in_progress",
  );

  return (
    <main className="barista">
      <header className="barista-header">
        <div>
          <p className="eyebrow">quầy · counter</p>
          <h1>ORDER BOARD</h1>
        </div>
        <div className="barista-controls">
          {permission === "default" && (
            <button
              type="button"
              className="ghost"
              onClick={async () => {
                const gate = browserGate();
                await gate.requestPermission();
                setPermission(gate.permission());
              }}
            >
              Enable notifications
            </button>
          )}
          <button
            type="button"
            className="ghost"
            aria-pressed={muted}
            onClick={() => {
              const next = !muted;
              setMuted(window.localStorage, next);
              setMutedState(next);
            }}
          >
            {muted ? "Unmute chime" : "Mute chime"}
          </button>
        </div>
      </header>

      <div className="lanes">
        <Lane title="New" count={newOrders.length}>
          {newOrders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              now={now}
              flash={flashIds.has(order.id)}
              onAct={act}
            />
          ))}
        </Lane>
        <Lane title="Making" count={making.length}>
          {making.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              now={now}
              flash={flashIds.has(order.id)}
              onAct={act}
            />
          ))}
        </Lane>
        <Lane title="Done" count={board.done.length}>
          {board.done.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              now={now}
              flash={false}
              onAct={act}
            />
          ))}
        </Lane>
      </div>
    </main>
  );
}

function Lane({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="lane" data-lane={title.toLowerCase()}>
      <div className="lane-head">
        <h2>{title}</h2>
        <span className="lane-count">{count}</span>
      </div>
      <div className="lane-body">{children}</div>
    </section>
  );
}

function OrderCard({
  order,
  now,
  flash,
  onAct,
}: {
  order: Order;
  now: number;
  flash: boolean;
  onAct: (
    order: Order,
    action: "start" | "complete" | "cancel",
  ) => Promise<void>;
}) {
  return (
    <article
      className={`order-card status-${order.status} ${flash ? "flash" : ""}`}
    >
      <div className="card-line">
        <span className="order-number">#{order.orderNumber}</span>
        {order.customerName && (
          <span className="customer-name">{order.customerName}</span>
        )}
        <span className="elapsed">{elapsedOf(order.createdAt, now)}</span>
      </div>
      <ul className="card-items">
        {order.items.map((line, index) => (
          <li key={index}>
            <span className="quantity">{line.quantity}×</span>{" "}
            {line.itemNameVi}
            <span className="detail">
              {" "}
              {line.temperature === "hot" ? "nóng" : "đá"}
              {line.milkOptionName && ` · ${line.milkOptionName}`}
              {line.sweetenerTypeName && ` · ${line.sweetenerTypeName}`}
              {line.sweetnessLevelName && ` · ${line.sweetnessLevelName}`}
              {line.coldFoamName && ` · ${line.coldFoamName}`}
            </span>
            {line.notes && <span className="notes">“{line.notes}”</span>}
          </li>
        ))}
      </ul>
      <div className="card-actions">
        {order.status === "placed" && (
          <button type="button" onClick={() => void onAct(order, "start")}>
            Start
          </button>
        )}
        {(order.status === "placed" || order.status === "in_progress") && (
          <button type="button" onClick={() => void onAct(order, "complete")}>
            Complete
          </button>
        )}
        {order.status === "placed" && (
          <button
            type="button"
            className="ghost"
            onClick={() => void onAct(order, "cancel")}
          >
            Cancel
          </button>
        )}
      </div>
    </article>
  );
}
