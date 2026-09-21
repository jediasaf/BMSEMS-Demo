import { test, expect, type Page, type ConsoleMessage } from '@playwright/test';

/**
 * The interview demo, driven end to end.
 *
 * `/interview/verify` already asserts that the *numbers* hold. This asserts
 * that a person can get to them: that the guided demo navigates, that each
 * claim is actually on screen, and that nothing throws on the way. The two
 * together are what "the demo works every time" means.
 */

const API = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8000';

/** Fails the test on any page error or console error, wherever it happens. */
function watchForErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`));
  page.on('console', (message: ConsoleMessage) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
  return errors;
}

async function nextStep(page: Page) {
  await page
    .getByRole('button', { name: /Next demo step/i })
    .first()
    .click();
  await page.waitForLoadState('networkidle').catch(() => undefined);
  await page.waitForTimeout(600);
}

test.describe('interview demo path', () => {
  test('the twelve curated steps run without errors', async ({ page }) => {
    const errors = watchForErrors(page);

    await page.goto('/bms');
    await expect(page.getByRole('heading', { name: 'AI Building Operator' })).toBeVisible();

    // 1 — Interview Mode, preloaded, and the guided demo opens.
    await page
      .getByRole('button', { name: /Start demo/i })
      .first()
      .click();
    await expect(page.getByText(/step 1 of 12/i)).toBeVisible();
    await expect(page.getByText(/Interview mode/i).first()).toBeVisible();

    // 2 — the injected scenario is applied and labelled as injected.
    await nextStep(page);
    await expect(page.getByText(/step 2 of 12/i)).toBeVisible();
    await expect(page.getByText(/injected scenario/i).first()).toBeVisible();

    // 3 — an anomaly exists, with observed, expected and possible causes.
    await nextStep(page);
    await expect(page).toHaveURL(/\/bms\/ai-operations/);
    await expect(page.getByText(/insight feed/i)).toBeVisible();
    await expect(page.getByText(/Observed/i).first()).toBeVisible();
    await expect(page.getByText(/Expected/i).first()).toBeVisible();
    await expect(page.getByText(/possible causes/i).first()).toBeVisible();
    await expect(page.getByText(/not a diagnosis/i).first()).toBeVisible();

    // 4 — a recommendation, which claims no saving before simulation.
    await nextStep(page);
    await expect(page.getByText(/AI recommendation/i).first()).toBeVisible();
    // The claim, not the sentence that used to carry it: nothing is asserted
    // about savings until the simulator has run both cases.
    await expect(page.getByText(/not claimed until simulated/i)).toBeVisible();

    // 5 — the Control Lab: before/after, and the simulator's verdict.
    await nextStep(page);
    await expect(page).toHaveURL(/\/bms\/control-lab/);
    await expect(page.getByText(/simulation mode/i).first()).toBeVisible();
    await expect(page.getByText(/Baseline vs AI control/i)).toBeVisible();
    await expect(page.getByText(/Simulator verdict/i)).toBeVisible();
    await expect(page.getByText(/^accepted$/i).first()).toBeVisible();
    await expect(page.getByText(/HVAC energy/i).first()).toBeVisible();
    await expect(page.getByText(/Comfort violation/i).first()).toBeVisible();

    // 6 — EMS portfolio.
    await nextStep(page);
    await expect(page).toHaveURL(/\/ems$/);
    await expect(page.getByRole('heading', { name: /AI Power Operator/i })).toBeVisible();
    await expect(page.getByText(/Facility performance/i)).toBeVisible();

    // 7 — the EV surge is applied.
    await nextStep(page);
    await expect(page).toHaveURL(/\/ems\/scenario-lab/);
    await expect(page.getByText(/EV charging surge/i).first()).toBeVisible();

    // 8 — the network shows the overload.
    await nextStep(page);
    await expect(page).toHaveURL(/\/ems\/network/);
    await expect(page.getByText(/overload risk/i).first()).toBeVisible();
    await expect(page.getByText(/single line diagram/i)).toBeVisible();

    // 9 — run the optimiser from the Scenario Lab.
    await nextStep(page);
    await expect(page).toHaveURL(/\/ems\/scenario-lab/);
    await page
      .getByRole('button', { name: /Run optimisation/i })
      .first()
      .click();
    await expect(page.getByText(/Flexible-load dispatch/i)).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText(/Constraint satisfied/i)).toBeVisible();

    // 10 — verified by an independent load flow, back under the limit, and
    // the post-action network gate says so rather than the solver.
    await nextStep(page);
    await expect(page.getByText(/Verified by load flow/i)).toBeVisible();
    const after = await page.getByTestId('loading-after').first().textContent();
    expect(Number.parseFloat((after ?? '').replace('%', ''))).toBeLessThan(100);
    // By role, not by text: the guided-demo caption mentions the panel by name
    // too, and a locator that matches the narration as well as the thing it
    // narrates is not testing the thing.
    await expect(page.getByRole('heading', { name: 'Network verdict' })).toBeVisible();
    await expect(page.getByText(/transformer loading stays at or below/i)).toBeVisible();
    await expect(page.getByText(/EV energy is conserved, not shed/i)).toBeVisible();
    await expect(page.getByText(/second pandapower solve/i).first()).toBeVisible();

    // 11 — provenance.
    await nextStep(page);
    await expect(page).toHaveURL(/\/bms$/);
    await page
      .getByRole('button', { name: /Data provenance/i })
      .first()
      .click();
    await expect(page.getByRole('dialog', { name: /Data provenance/i })).toBeVisible();
    await page.keyboard.press('Escape');

    // 12 — the architecture drawer closes the demo.
    await nextStep(page);
    await expect(page.getByRole('dialog', { name: /Architecture/i })).toBeVisible();
    await expect(page.getByText(/Provenance vocabulary/i)).toBeVisible();

    expect(errors, `console/page errors during the demo:\n${errors.join('\n')}`).toEqual([]);
  });

  test('reset returns the product to its opening position', async ({ page }) => {
    const errors = watchForErrors(page);

    await page.goto('/ems/scenario-lab');
    await page
      .getByRole('button', { name: /EV Charging Surge/i })
      .first()
      .click();
    await page.waitForTimeout(1500);
    await page
      .getByRole('button', { name: /Run optimisation/i })
      .first()
      .click();
    await expect(page.getByText(/Flexible-load dispatch/i)).toBeVisible({ timeout: 90_000 });

    await page
      .getByRole('button', { name: /Reset demo/i })
      .first()
      .click();
    await expect(page).toHaveURL(/\/bms$/);

    // The optimisation is gone, and the scenario is back to the baseline.
    await page.goto('/ems/scenario-lab');
    await expect(page.getByText(/Flexible-load dispatch/i)).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Normal Day/i }).first()).toHaveAttribute(
      'data-active',
      'true',
    );

    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('a normal day stays honestly empty', async ({ page }) => {
    const errors = watchForErrors(page);

    await page.goto('/bms');
    await page
      .getByRole('button', { name: /Normal Day/i })
      .first()
      .click();
    await page.waitForLoadState('networkidle').catch(() => undefined);

    // No invented alerts: the empty state says monitoring is running.
    await expect(page.getByText(/No fault to act on/i)).toBeVisible();
    await expect(page.getByText(/Recommendations follow a material finding/i)).toBeVisible();
    // And the standing setpoint plan is still offered, because a quiet day is
    // not the same as a day with nothing to gain. The two panels sit next to
    // each other, so they must not read as contradicting one another.
    await expect(page.getByRole('heading', { name: /^Optimisation$/i })).toBeVisible();

    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('the dashboard says what is coming and what to do about it', async ({ page }) => {
    const errors = watchForErrors(page);

    await page.goto('/bms');
    await page
      .getByRole('button', { name: /Hot Day/i })
      .first()
      .click();
    await page.waitForLoadState('networkidle').catch(() => undefined);

    // Forward-looking: a predicted peak with the interval it came with, not a
    // point estimate on its own.
    const forecast = page.locator('section', {
      has: page.getByRole('heading', { name: /^Forecast$/i }),
    });
    await expect(forecast.getByText(/Predicted peak/i)).toBeVisible();
    await expect(forecast.getByText(/^-?[\d,.]+ kW$/).first()).toBeVisible();
    await expect(forecast.getByText(/80% interval/i)).toBeVisible();
    await expect(forecast.getByText(/^[\d,.]+–[\d,.]+$/).first()).toBeVisible();

    // Actionable: what the optimiser would do, and whether the simulator
    // accepted it. A verdict is required -- an optimiser that cannot be told
    // no is not a gate.
    const optimisation = page.locator('section', {
      has: page.getByRole('heading', { name: /^Optimisation$/i }),
    });
    await expect(optimisation.getByText(/HVAC energy/i)).toBeVisible();
    await expect(optimisation.getByText(/^[+-][\d.]+%$/).first()).toBeVisible();
    await expect(optimisation.getByText(/^(Accepted|Rejected)$/i)).toBeVisible();

    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('the backend agrees the demo is ready', async ({ request }) => {
    // A snapshot build has no backend to ask. The recording carries the
    // verdict from when it was taken, and scripts/verify_snapshot.py re-checks
    // it; skipping here keeps this test about the live path it was written for.
    test.skip(process.env.E2E_SNAPSHOT === '1', 'snapshot build has no backend');
    // A host that scales to zero answers the first request with a 502 while
    // the machine wakes, and this is the most expensive endpoint in the
    // product (~2 s warm, ~23 s from cold). Retry the wake, not the verdict:
    // the assertions below are unchanged, and a backend that is genuinely
    // unwell still fails.
    let response = await request.get(`${API}/interview/verify`, { timeout: 120_000 });
    for (let attempt = 0; attempt < 3 && !response.ok(); attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 10_000));
      response = await request.get(`${API}/interview/verify`, { timeout: 120_000 });
    }
    expect(response.ok(), `GET /interview/verify -> ${response.status()}`).toBeTruthy();
    const body = await response.json();
    const failed = (body.checks as { check: string; passed: boolean; detail: string }[])
      .filter((check) => !check.passed)
      .map((check) => `${check.check}: ${check.detail}`);
    expect(failed, failed.join('\n')).toEqual([]);
    expect(body.ready).toBe(true);
  });
});
