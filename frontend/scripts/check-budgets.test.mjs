/**
 * Lightweight checks for budget evaluation helpers (no Vite build required).
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

function evaluate(budget, bytes) {
  let status = "ok";
  if (bytes > budget.maxBytes) status = "fail";
  else if (bytes > budget.warnBytes) status = "warn";
  return status;
}

describe("budget thresholds", () => {
  const budget = { warnBytes: 100, maxBytes: 120 };

  it("is ok under warn", () => {
    assert.equal(evaluate(budget, 99), "ok");
  });

  it("warns between warn and max", () => {
    assert.equal(evaluate(budget, 110), "warn");
  });

  it("fails above max", () => {
    assert.equal(evaluate(budget, 121), "fail");
  });
});
