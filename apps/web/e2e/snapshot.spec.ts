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
  /**
   * The replay cursor has to land on the same hour the clock shows, from any
   * timezone.
   *
   * The recorded timestamps carry no offset, so they are parsed in the
   * viewer's local frame. Writing them back with toISOString() converted them
   * to UTC, which shifted every request by the viewer's offset: a 404 at the
   * edges of the replay window, and -- far worse -- correct-looking data from
   * the wrong hour in the middle of it. It passed on a UTC machine and failed
   * at UTC+8, so this runs somewhere that is not UTC.
   */
  test('the replay cursor is right from a non-UTC timezone', async ({ browser }) => {
    test.skip(process.env.E2E_SNAPSHOT !== '1', 'needs a NEXT_PUBLIC_SNAPSHOT=1 build');

    const context = await browser.newContext({
      timezoneId: 'Asia/Singapore',
      viewport: { width: 1600, height: 1000 },
    });
    const page = await context.newPage();
    const missing = new Set<string>();
    page.on('response', (r) => {
      if (r.status() === 404) missing.add(new URL(r.url()).pathname);
    });

    await page.goto('/ems');
    await page.waitForLoadState('networkidle').catch(() => undefined);
    await expect(page.getByText(/Panel unavailable/i)).toHaveCount(0);

    // Walk the cursor across the window, including the first hours, which is
    // where the shift pushed requests off the start of the recording.
    const slider = page.getByRole('slider', { name: /Replay position/i }).first();
    for (const value of ['0', '29', '96', '200']) {
      await slider.fill(value);
      await page.waitForTimeout(900);
      await expect(page.getByText(/Panel unavailable/i)).toHaveCount(0);
    }

    expect(
      [...missing],
      `recorded files requested and not found:\n${[...missing].join('\n')}`,
    ).toEqual([]);
    await context.close();
  });

  /**
   * Every site the selector offers has to be in the recording.
   *
   * The recorder captured only the default site while the Building dropdown
   * listed six and the facility table invited a click on any row, so the
   * first thing a curious viewer did returned a 404. A control that offers a
   * choice the recording cannot serve is the defect, so this walks all of
   * them.
   */
  test('every site in the selector is recorded', async ({ page }) => {
    test.skip(process.env.E2E_SNAPSHOT !== '1', 'needs a NEXT_PUBLIC_SNAPSHOT=1 build');

    const missing = new Set<string>();
    page.on('response', (r) => {
      if (r.status() === 404) missing.add(new URL(r.url()).pathname);
    });

    await page.goto('/bms');
    await page.waitForLoadState('networkidle').catch(() => undefined);

    const selector = page.getByRole('combobox').first();
    const values = await selector
      .locator('option')
      .evaluateAll((os) => os.map((o) => (o as HTMLOptionElement).value));
    expect(values.length, 'the building selector should offer more than one site').toBeGreaterThan(
      1,
    );

    for (const value of values) {
      await selector.selectOption(value);
      await page.waitForLoadState('networkidle').catch(() => undefined);
      await page.waitForTimeout(700);
      await expect(
        page.getByText(/Panel unavailable/i),
        `site ${value} has no recorded data`,
      ).toHaveCount(0);
    }

    // And the facility drill-down the portfolio table invites.
    await page.goto('/ems');
    await page.waitForLoadState('networkidle').catch(() => undefined);
    const rows = page.locator('table tbody tr');
    const count = await rows.count();
    expect(count, 'the portfolio should list facilities').toBeGreaterThan(1);
    for (let i = 0; i < count; i += 1) {
      await page.goto('/ems');
      await page.waitForLoadState('networkidle').catch(() => undefined);
      await rows.nth(i).click();
      await page.waitForLoadState('networkidle').catch(() => undefined);
      await page.waitForTimeout(700);
      await expect(page.getByText(/Panel unavailable/i)).toHaveCount(0);
    }

    expect(
      [...missing],
      `recorded files requested and not found:\n${[...missing].join('\n')}`,
    ).toEqual([]);
  });

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
    await expect(page.getByRole('heading', { name: 'Building Operator' })).toBeVisible();
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
