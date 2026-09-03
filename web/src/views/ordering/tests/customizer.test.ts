import { describe, expect, it } from "vitest";
import type { MenuItem } from "../../../api/client";
import { menuDocument } from "../lib/menuData";
import {
  changeTemperature,
  groupsForItem,
  initialSelection,
  offeredTemperatures,
  resolveDefault,
  selectOption,
  selectionToLine,
  visibleGroups,
} from "../lib/customizer";

function item(id: string): MenuItem {
  const found = menuDocument.items.find((candidate) => candidate.id === id);
  if (!found) {
    throw new Error(`test fixture: unknown item "${id}"`);
  }
  return found;
}

describe("customizer constraint derivation", () => {
  it("limits temperatures to the item's offered set", () => {
    expect(offeredTemperatures(item("sua-da"))).toEqual(["hot", "iced"]);
    expect(offeredTemperatures(item("cortado"))).toEqual(["hot"]);
    expect(offeredTemperatures(item("kem-sua"))).toEqual(["iced"]);
  });

  it("filters modifier groups to the item's allowance", () => {
    expect(groupsForItem(menuDocument, "sua-da").map((g) => g.id)).toEqual([
      "sweetness",
      "cold-foam",
    ]);
    expect(groupsForItem(menuDocument, "cortado").map((g) => g.id)).toEqual([
      "milk-cortado",
    ]);
    expect(groupsForItem(menuDocument, "kem-sua")).toEqual([]);
  });

  it("hides cold foam groups while the drink is hot (foam gating)", () => {
    const hot = visibleGroups(menuDocument, item("matcha-sua"), "hot");
    const iced = visibleGroups(menuDocument, item("matcha-sua"), "iced");

    expect(hot.map((view) => view.group.id)).not.toContain("cold-foam");
    expect(iced.map((view) => view.group.id)).toContain("cold-foam");
  });

  it("filters group options to those offered at the temperature", () => {
    const hot = visibleGroups(menuDocument, item("matcha-sua"), "hot").find(
      (view) => view.group.id === "milk-matcha-latte",
    );
    const iced = visibleGroups(menuDocument, item("matcha-sua"), "iced").find(
      (view) => view.group.id === "milk-matcha-latte",
    );

    expect(hot?.options.map((o) => o.id)).toEqual(["whole-milk", "oat-milk"]);
    expect(iced?.options.map((o) => o.id)).toEqual([
      "oat-milk",
      "milk-plus-cream",
      "heavy-cream",
      "half-and-half",
    ]);
  });

  it("resolves defaults from the defaultOptionId shape", () => {
    const sweetness = menuDocument.modifierGroups.find(
      (group) => group.id === "sweetness",
    );
    expect(sweetness && resolveDefault(sweetness, "hot")).toBe("full");
    expect(sweetness && resolveDefault(sweetness, "iced")).toBe("full");
  });

  it("resolves defaults from the defaultByTemperature shape", () => {
    const milk = menuDocument.modifierGroups.find(
      (group) => group.id === "milk-matcha-latte",
    );
    expect(milk && resolveDefault(milk, "hot")).toBe("whole-milk");
    expect(milk && resolveDefault(milk, "iced")).toBe("milk-plus-cream");
  });

  it("builds the initial selection from the item's first temperature and defaults", () => {
    const selection = initialSelection(menuDocument, item("matcha-sua"));

    expect(selection).toEqual({
      itemId: "matcha-sua",
      temperature: "hot",
      milkOptionId: "whole-milk",
      sweetenerTypeId: "condensed-milk",
      sweetnessLevelId: "full",
      coldFoamId: null,
      notes: "",
    });
  });

  it("leaves customization fields empty for a plain iced-only item", () => {
    const selection = initialSelection(menuDocument, item("kem-sua"));

    expect(selection).toEqual({
      itemId: "kem-sua",
      temperature: "iced",
      milkOptionId: null,
      sweetenerTypeId: null,
      sweetnessLevelId: null,
      coldFoamId: null,
      notes: "",
    });
  });

  it("resets selections the new temperature does not offer", () => {
    const hot = initialSelection(menuDocument, item("matcha-sua"));

    const iced = changeTemperature(menuDocument, item("matcha-sua"), hot, "iced");

    expect(iced.milkOptionId).toBe("milk-plus-cream");
    expect(iced.sweetenerTypeId).toBe("condensed-milk");
  });

  it("keeps selections that remain valid at the new temperature", () => {
    const hot = selectOption(
      initialSelection(menuDocument, item("matcha-sua")),
      "milk",
      "oat-milk",
    );

    const iced = changeTemperature(menuDocument, item("matcha-sua"), hot, "iced");

    expect(iced.milkOptionId).toBe("oat-milk");
  });

  it("clears the cold foam choice when switching back to hot", () => {
    const iced = selectOption(
      changeTemperature(
        menuDocument,
        item("matcha-sua"),
        initialSelection(menuDocument, item("matcha-sua")),
        "iced",
      ),
      "cold_foam",
      "foam-salted",
    );
    expect(
      changeTemperature(menuDocument, item("matcha-sua"), iced, "hot")
        .coldFoamId,
    ).toBeNull();
  });

  it("snapshots the full selection as an order line with trimmed notes", () => {
    const iced = changeTemperature(
      menuDocument,
      item("matcha-sua"),
      initialSelection(menuDocument, item("matcha-sua")),
      "iced",
    );

    const line = selectionToLine(
      { ...iced, notes: "  extra cold  " },
      3,
    );

    expect(line).toEqual({
      itemId: "matcha-sua",
      temperature: "iced",
      quantity: 3,
      milkOptionId: "milk-plus-cream",
      sweetenerTypeId: "condensed-milk",
      sweetnessLevelId: "full",
      coldFoamId: null,
      notes: "extra cold",
    });
    expect(selectionToLine({ ...iced, notes: "   " }, 1).notes).toBeNull();
  });
});
