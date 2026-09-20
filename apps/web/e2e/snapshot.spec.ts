import { test, expect, type ConsoleMessage } from '@playwright/test';

/**
 * The recording has to drive the whole demo with nothing behind it.
 *
 * The failure this guards against is specific and was real: the filenames the
 * recorder writes and the filenames the browser asks for are produced by two
 * implementations in two languages, and when they disagree the product shows
 * error panels instead of data. A 404 here is that disagreement.
 *
 * Only meaningful against a build made with NEXT_PUBLIC_SNAPSHOT=1, so it opts
 * in rather than failing everywhere else.
 */
test.describe('static recording', () => {
  test('drives the whole demo with no backend', async ({ page }) => {
    test.skip(process.env.E2E_SNAPSHOT !== '1', 'needs a NEXT_PUBLIC_SNAPSHOT=1 build');

    const errors: string[] = [];
    const missing = new Set<string>();
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    page.on('console', (m: ConsoleMessage) => {
      if (m.type() === 'error') errors.push(`console: ${m.text()}`);
    });
    page.on('response', (r) => {
      if (r.status() === 404) missing.add(new URL(r.url()).pathname);
    });

    await page.goto('/bms');
    await expect(page.getByRole('heading', { name: 'AI Building Operator' })).toBeVisible();
    // The build must say what it is. A replay presented as live is the one
    // failure this project does not tolerate.
    await expect(page.getByText(/Recorded/i).first()).toBeVisible();
    // And it must actually render measurements. A recording whose filenames
    // do not match what the browser asks for still loads the page: every panel
    // just renders its error state instead of data, which is exactly the
    // failure that prompted this test.
    await expect(page.getByText(/Panel unavailable/i)).toHaveCount(0);
    await expect(page.getByText(/^-?[\d,.]+ kW$/).first()).toBeVisible();

    await page
      .getByRole('button', { name: /Start demo/i })
      .first()
      .click();
    await expect(page.getByText(/step 1 of 12/i)).toBeVisible();
    for (let i = 0; i < 11; i += 1) {
      await page
        .getByRole('button', { name: /Next demo step/i })
        .first()
        .click();
      await page.waitForTimeout(700);
    }
    await expect(page.getByText(/step 12 of 12/i)).toBeVisible();

    // The EMS optimisation is the most expensive thing the product does, and
    // the most tempting thing to fake. Recorded, it still has to come back
    // under capacity.
    await page.goto('/ems/scenario-lab');
    await page
      .getByRole('button', { name: /EV Charging Surge/i })
      .first()
      .click();
    await page.waitForTimeout(1200);
    await page
      .getByRole('button', { name: /Run optimisation/i })
      .first()
      .click();
    await expect(page.getByText(/Flexible-load dispatch/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Panel unavailable/i)).toHaveCount(0);
    const after = await page.getByTestId('loading-after').first().textContent();
    expect(Number.parseFloat((after ?? '').replace('%', ''))).toBeLessThan(100);

    expect(
      [...missing],
      `snapshot files the browser asked for and did not get:\n${[...missing].join('\n')}`,
    ).toEqual([]);
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
