import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type {
  ApiClient,
  MenuDocument,
  MenuItem,
  Order,
  ServerEvent,
  Temperature,
} from "../../api/client";
import type { CartLine } from "../../state/cart";
import { createCartReducer, lineKey } from "../../state/cart";
import { guestOrderReducer, guestStatusCopy } from "../../state/ordering-status";
import {
  loadHistory,
  recordOrder,
  reorderLines,
  type HistoryEntry,
} from "../../state/order-history";
import { createDevClient } from "./lib/devClient";
import {
  changeTemperature,
  initialSelection,
  selectOption,
  selectionToLine,
  visibleGroups,
  type Selection,
} from "./lib/customizer";
import { buildOrderCreate } from "./lib/payload";
import { browserNotificationWindow, createReadyNotifier } from "./lib/notify";
import "./ordering.css";

type CartActionLike = Parameters<ReturnType<typeof createCartReducer>>[1];

function itemById(menu: MenuDocument, itemId: string): MenuItem | undefined {
  return menu.items.find((item) => item.id === itemId);
}

function optionName(menu: MenuDocument, optionId: string | null): string | null {
  if (optionId === null) {
    return null;
  }
  for (const group of menu.modifierGroups) {
    const option = group.options.find((candidate) => candidate.id === optionId);
    if (option) {
      return option.name;
    }
  }
  return null;
}

function lineSummary(menu: MenuDocument, line: CartLine): string {
  const parts = [
    line.temperature === "hot" ? "hot" : "iced",
    optionName(menu, line.milkOptionId),
    optionName(menu, line.sweetenerTypeId),
    optionName(menu, line.sweetnessLevelId),
    optionName(menu, line.coldFoamId),
  ].filter((part): part is string => part !== null);
  if (line.notes) {
    parts.push(`"${line.notes}"`);
  }
  return parts.join(" · ");
}

function clockOf(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function OrderingPage({
  client = createDevClient(),
}: {
  client?: ApiClient;
}) {
  const [menu, setMenu] = useState<MenuDocument | null>(null);
  const [cart, dispatchCart] = useReducer(
    (state: CartLine[], action: CartActionLike) => {
      if (!menu) {
        return state;
      }
      return createCartReducer(menu.orderRules)(state, action);
    },
    [],
  );
  const [customizerItem, setCustomizerItem] = useState<MenuItem | null>(null);
  const [cartOpen, setCartOpen] = useState(false);
  const [customerName, setCustomerName] = useState("");
  const [guestOrder, dispatchGuestOrder] = useReducer(guestOrderReducer, null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [notifyAvailable] = useState(() => browserNotificationWindow() !== null);
  const [notifyOptedIn, setNotifyOptedIn] = useState(false);
  const notificationWindow = useRef(browserNotificationWindow()).current;
  const notifier = useRef(
    notificationWindow === null
      ? null
      : createReadyNotifier(notificationWindow),
  );

  useEffect(() => {
    let cancelled = false;
    client.getMenu().then((loaded) => {
      if (!cancelled) {
        setMenu(loaded);
        setHistory(loadHistory(window.localStorage));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(
    () =>
      client.subscribeToEvents((event: ServerEvent) => {
        if (event.type === "order:status") {
          dispatchGuestOrder({ type: "feed", event });
          notifier.current?.onOrderStatus(event.order);
        }
      }),
    [client],
  );

  useEffect(() => {
    if (!guestOrder) {
      return;
    }
    let cancelled = false;
    client.getOrder(guestOrder.id).then((order) => {
      if (!cancelled) {
        dispatchGuestOrder({ type: "refetched", order });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, guestOrder?.id]);

  const cartCount = useMemo(
    () => cart.reduce((total, line) => total + line.quantity, 0),
    [cart],
  );

  const placeOrder = useCallback(async () => {
    if (cart.length === 0 || !menu) {
      return;
    }
    const order = await client.placeOrder(
      buildOrderCreate(cart, customerName),
    );
    setHistory(recordOrder(window.localStorage, order));
    dispatchCart({ type: "clear" });
    setCartOpen(false);
    setCustomerName("");
    dispatchGuestOrder({ type: "tracked", order });
  }, [cart, client, customerName, menu]);

  const reorder = useCallback(
    (entry: HistoryEntry) => {
      if (!menu) {
        return;
      }
      for (const line of reorderLines(menu, entry)) {
        dispatchCart({ type: "add", line });
      }
      setHistoryOpen(false);
      setCartOpen(true);
    },
    [menu],
  );

  const optInToNotifications = useCallback(async () => {
    const granted = (await notifier.current?.optIn()) ?? false;
    setNotifyOptedIn(granted);
  }, []);

  if (menu === null) {
    return (
      <main className="ordering loading">
        <p>Đang tải thực đơn…</p>
      </main>
    );
  }

  return (
    <main className="ordering">
      <header className="ordering-header">
        <div>
          <p className="eyebrow">nhà làm · quán nhà</p>
          <h1>CAFE ÔNG THỌ</h1>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="ghost"
            onClick={() => setHistoryOpen(true)}
          >
            Your orders
          </button>
          <button
            type="button"
            className="cart-button"
            onClick={() => setCartOpen(true)}
          >
            Cart
            {cartCount > 0 && <span className="cart-count">{cartCount}</span>}
          </button>
        </div>
      </header>

      {guestOrder && <StatusPanel order={guestOrder} onNotify={notifyAvailable && !notifyOptedIn ? optInToNotifications : undefined} notifyOptedIn={notifyOptedIn} onDismiss={() => dispatchGuestOrder({ type: "cleared" })} />}

      {menu.categories.map((category) => {
        const items = menu.items.filter(
          (item) => item.categoryId === category.id,
        );
        if (items.length === 0) {
          return null;
        }
        return (
          <section key={category.id} className="menu-section">
            <div className="section-head">
              <h2>{category.nameVi}</h2>
              <span className="section-en">{category.name}</span>
            </div>
            <div className="items">
              {items.map((item) => (
                <ItemCard
                  key={item.id}
                  item={item}
                  onCustomize={() => setCustomizerItem(item)}
                />
              ))}
            </div>
          </section>
        );
      })}

      {customizerItem && (
        <CustomizerSheet
          menu={menu}
          item={customizerItem}
          onClose={() => setCustomizerItem(null)}
          onAdd={(line) => {
            dispatchCart({ type: "add", line });
            setCustomizerItem(null);
            setCartOpen(true);
          }}
        />
      )}

      {cartOpen && (
        <CartSheet
          menu={menu}
          cart={cart}
          customerName={customerName}
          onCustomerName={setCustomerName}
          onQuantity={(key, quantity) =>
            dispatchCart({ type: "setQuantity", key, quantity })
          }
          onRemove={(key) => dispatchCart({ type: "remove", key })}
          onPlace={placeOrder}
          onClose={() => setCartOpen(false)}
        />
      )}

      {historyOpen && (
        <HistorySheet
          client={client}
          entries={history}
          onReorder={reorder}
          onClose={() => setHistoryOpen(false)}
        />
      )}
    </main>
  );
}

function StatusPanel({
  order,
  onNotify,
  notifyOptedIn,
  onDismiss,
}: {
  order: Order;
  onNotify: (() => Promise<void>) | undefined;
  notifyOptedIn: boolean;
  onDismiss: () => void;
}) {
  return (
    <aside className="status-panel" data-status={order.status}>
      <div className="status-line">
        <span className="order-number">#{order.orderNumber}</span>
        <span className="status-chip">{guestStatusCopy(order.status)}</span>
      </div>
      <ul>
        {order.items.map((line, index) => (
          <li key={index}>
            {line.quantity}× {line.itemNameVi}
          </li>
        ))}
      </ul>
      <div className="status-actions">
        {onNotify && order.status !== "completed" && (
          <button type="button" onClick={onNotify}>
            Notify me when ready
          </button>
        )}
        {notifyOptedIn && order.status !== "completed" && (
          <span className="muted">We will ping you when it is ready</span>
        )}
        <button type="button" className="ghost" onClick={onDismiss}>
          Close
        </button>
      </div>
    </aside>
  );
}

function ItemCard({
  item,
  onCustomize,
}: {
  item: MenuItem;
  onCustomize: () => void;
}) {
  return (
    <button type="button" className="item-card" onClick={onCustomize}>
      <ItemTile item={item} />
      <div className="item-body">
        <div className="item-line">
          <span className="item-name">{item.nameVi}</span>
          <span className="tags">
            {item.temperatures.includes("hot") && (
              <span className="pill pill-nong">nóng</span>
            )}
            {item.temperatures.includes("iced") && (
              <span className="pill pill-da">đá</span>
            )}
          </span>
        </div>
        <p className="item-desc">{item.description}</p>
        <span className="item-cta">Customize</span>
      </div>
    </button>
  );
}

function ItemTile({ item }: { item: MenuItem }) {
  if (item.imagePath) {
    return (
      <img
        className="item-photo"
        src={item.imagePath}
        alt={item.nameVi}
        loading="lazy"
      />
    );
  }
  return (
    <span className="item-placeholder" aria-hidden="true">
      {item.nameVi.charAt(0)}
    </span>
  );
}

function Sheet({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sheet-head">
          <h3>{title}</h3>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function CustomizerSheet({
  menu,
  item,
  onClose,
  onAdd,
}: {
  menu: MenuDocument;
  item: MenuItem;
  onClose: () => void;
  onAdd: (line: CartLine) => void;
}) {
  const [selection, setSelection] = useState<Selection>(() =>
    initialSelection(menu, item),
  );
  const [quantity, setQuantity] = useState(1);
  const groups = visibleGroups(menu, item, selection.temperature);

  const setTemperature = (temperature: Temperature) => {
    setSelection(changeTemperature(menu, item, selection, temperature));
  };

  return (
    <Sheet title={item.nameVi} onClose={onClose}>
      <div className="customizer">
        <div className="option-row" role="group" aria-label="Temperature">
          {item.temperatures.map((temperature) => (
            <button
              key={temperature}
              type="button"
              className={`option-pill ${selection.temperature === temperature ? "selected" : ""}`}
              onClick={() => setTemperature(temperature)}
            >
              {temperature === "hot" ? "nóng" : "đá"}
            </button>
          ))}
        </div>

        {groups.map(({ group, options, defaultOptionId }) => {
          const current =
            selection[
              group.dimension === "milk"
                ? "milkOptionId"
                : group.dimension === "sweetener_type"
                  ? "sweetenerTypeId"
                  : group.dimension === "sweetness_level"
                    ? "sweetnessLevelId"
                    : "coldFoamId"
            ];
          return (
            <fieldset key={group.id} className="option-group">
              <legend>{group.name}</legend>
              <div className="option-row">
                {options.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={`option-pill ${current === option.id ? "selected" : ""}`}
                    onClick={() =>
                      setSelection(
                        selectOption(
                          selection,
                          group.dimension,
                          current === option.id && !group.required
                            ? null
                            : option.id,
                        ),
                      )
                    }
                    aria-pressed={current === option.id}
                  >
                    {option.name}
                    {defaultOptionId === option.id && (
                      <span className="default-dot" title="default" />
                    )}
                  </button>
                ))}
              </div>
            </fieldset>
          );
        })}

        <label className="notes-row">
          Notes
          <textarea
            rows={2}
            maxLength={menu.orderRules.notesMaxLength}
            value={selection.notes}
            onChange={(event) =>
              setSelection({ ...selection, notes: event.target.value })
            }
            placeholder="anything the barista should know"
          />
        </label>

        <div className="quantity-row">
          <button
            type="button"
            onClick={() => setQuantity((q) => Math.max(1, q - 1))}
          >
            −
          </button>
          <span>{quantity}</span>
          <button
            type="button"
            onClick={() =>
              setQuantity((q) => Math.min(menu.orderRules.maxQuantity, q + 1))
            }
          >
            +
          </button>
        </div>
      </div>
      <button
        type="button"
        className="primary"
        onClick={() => onAdd(selectionToLine(selection, quantity))}
      >
        Add to cart
      </button>
    </Sheet>
  );
}

function CartSheet({
  menu,
  cart,
  customerName,
  onCustomerName,
  onQuantity,
  onRemove,
  onPlace,
  onClose,
}: {
  menu: MenuDocument;
  cart: CartLine[];
  customerName: string;
  onCustomerName: (name: string) => void;
  onQuantity: (key: string, quantity: number) => void;
  onRemove: (key: string) => void;
  onPlace: () => void;
  onClose: () => void;
}) {
  return (
    <Sheet title="Cart" onClose={onClose}>
      {cart.length === 0 ? (
        <p className="muted">Nothing here yet.</p>
      ) : (
        <ul className="cart-lines">
          {cart.map((line) => {
            const key = lineKey(line);
            const item = itemById(menu, line.itemId);
            return (
              <li key={key} className="cart-line">
                <div>
                  <span className="item-name">{item?.nameVi ?? line.itemId}</span>
                  <span className="line-detail">
                    {lineSummary(menu, line)}
                  </span>
                </div>
                <div className="line-controls">
                  <button
                    type="button"
                    onClick={() => onQuantity(key, line.quantity - 1)}
                    disabled={line.quantity <= menu.orderRules.minQuantity}
                  >
                    −
                  </button>
                  <span>{line.quantity}</span>
                  <button
                    type="button"
                    onClick={() => onQuantity(key, line.quantity + 1)}
                    disabled={line.quantity >= menu.orderRules.maxQuantity}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => onRemove(key)}
                  >
                    Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <label className="name-row">
        Name for the counter
        <input
          value={customerName}
          onChange={(event) => onCustomerName(event.target.value)}
          placeholder="optional"
        />
      </label>
      <button
        type="button"
        className="primary"
        disabled={cart.length === 0}
        onClick={onPlace}
      >
        Place order
      </button>
    </Sheet>
  );
}

function HistorySheet({
  client,
  entries,
  onReorder,
  onClose,
}: {
  client: ApiClient;
  entries: HistoryEntry[];
  onReorder: (entry: HistoryEntry) => void;
  onClose: () => void;
}) {
  const [statuses, setStatuses] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      entries.map((entry) =>
        client
          .getOrder(entry.id)
          .then((order) => [entry.id, order.status] as const)
          .catch(() => [entry.id, "unknown"] as const),
      ),
    ).then((pairs) => {
      if (!cancelled) {
        setStatuses(Object.fromEntries(pairs));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [client, entries]);

  return (
    <Sheet title="Your orders" onClose={onClose}>
      {entries.length === 0 ? (
        <p className="muted">No orders on this device yet.</p>
      ) : (
        <ul className="history-list">
          {entries.map((entry) => (
            <li key={entry.id} className="history-entry">
              <div>
                <span className="order-number">#{entry.orderNumber}</span>
                <span className="line-detail">
                  {clockOf(entry.placedAt)} ·{" "}
                  {entry.items
                    .map((line) => `${line.quantity}× ${line.itemNameVi}`)
                    .join(", ")}
                  {statuses[entry.id] && ` · ${statuses[entry.id]}`}
                </span>
              </div>
              <button type="button" onClick={() => onReorder(entry)}>
                Reorder
              </button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}
