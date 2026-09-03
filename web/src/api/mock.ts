import type {
  ApiClient,
  ApiError,
  EventListener,
  MenuDocument,
  Order,
  OrderCreate,
  OrderStatus,
  ServerEvent,
} from "./client";

/**
 * One scripted outcome for the mock. Request methods consume steps in
 * order; event steps are broadcast to subscribers after their optional
 * delay. Scenario files that build scripts live next to the views they
 * serve, so this harness stays generic.
 */
export type MockStep =
  | { kind: "menu"; menu: MenuDocument }
  | { kind: "order"; order: Order }
  | { kind: "orders"; orders: Order[] }
  | { kind: "error"; error: ApiError }
  | { kind: "event"; event: ServerEvent; delayMs?: number };

export interface MockClient extends ApiClient {
  enqueue(...steps: MockStep[]): void;
  emit(event: ServerEvent): void;
}

export class MockScriptError extends Error {
  readonly payload?: ApiError;

  constructor(detail: string, payload?: ApiError) {
    super(`mock script: ${detail}`);
    this.name = "MockScriptError";
    this.payload = payload;
  }
}

type RequestKind = "menu" | "order" | "orders" | "error";

export function createMockClient(script: MockStep[] = []): MockClient {
  const queue: MockStep[] = [...script];
  const listeners = new Set<EventListener>();

  const deliver = (event: ServerEvent, delayMs?: number): void => {
    const send = () => {
      for (const listener of listeners) {
        listener(event);
      }
    };
    if (delayMs === undefined) {
      send();
      return;
    }
    setTimeout(send, delayMs);
  };

  function take<K extends RequestKind>(
    method: string,
    accepted: readonly K[],
  ): Extract<MockStep, { kind: K }> {
    for (;;) {
      const step = queue.shift();
      if (step === undefined) {
        throw new MockScriptError(`${method} called with an exhausted script`);
      }
      if (step.kind === "event") {
        deliver(step.event, step.delayMs);
        continue;
      }
      if (!(accepted as readonly string[]).includes(step.kind)) {
        throw new MockScriptError(
          `${method} expected a "${accepted.join('" or "')}" step but found "${step.kind}"`,
        );
      }
      // The guard above proves the kind; TS cannot correlate array
      // contents with the generic parameter.
      return step as Extract<MockStep, { kind: K }>;
    }
  }

  const fail = (method: string, error: ApiError): Promise<never> =>
    Promise.reject(new MockScriptError(`${method}: ${error.error}`, error));

  return {
    enqueue(...steps) {
      queue.push(...steps);
    },
    emit(event) {
      deliver(event);
    },
    getMenu() {
      const step = take("getMenu", ["menu"]);
      return Promise.resolve(step.menu);
    },
    placeOrder(_request: OrderCreate) {
      const step = take("placeOrder", ["order", "error"]);
      if (step.kind === "error") {
        return fail("placeOrder", step.error);
      }
      return Promise.resolve(step.order);
    },
    getOrder(orderId: string) {
      const step = take(`getOrder(${orderId})`, ["order", "error"]);
      if (step.kind === "error") {
        return fail(`getOrder(${orderId})`, step.error);
      }
      return Promise.resolve(step.order);
    },
    listActiveOrders() {
      const step = take("listActiveOrders", ["orders", "error"]);
      if (step.kind === "error") {
        return fail("listActiveOrders", step.error);
      }
      return Promise.resolve(step.orders);
    },
    transitionStatus(orderId: string, status: OrderStatus) {
      const name = `transitionStatus(${orderId}, ${status})`;
      const step = take(name, ["order", "error"]);
      if (step.kind === "error") {
        return fail(name, step.error);
      }
      return Promise.resolve(step.order);
    },
    subscribeToEvents(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
