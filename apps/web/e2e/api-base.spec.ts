import { test, expect } from '@playwright/test';

import { resolveApiBase } from '../lib/api';

/**
 * A production build that quietly falls back to 127.0.0.1 points every
 * visitor's page at their own machine: the deployment looks healthy, the
 * status bar stays hopeful, and nothing works. This is the regression test
 * for that, and it needs no browser.
 */
test.describe('API base resolution', () => {
  test('a configured base is used, trimmed of trailing slashes', () => {
    expect(
      resolveApiBase({ NEXT_PUBLIC_API_BASE: 'https://api.example.com/', NODE_ENV: 'production' }),
    ).toEqual({ base: 'https://api.example.com', configured: true });

    expect(
      resolveApiBase({
        NEXT_PUBLIC_API_BASE: 'https://api.example.com///',
        NODE_ENV: 'production',
      }),
    ).toEqual({ base: 'https://api.example.com', configured: true });
  });

  test('development may fall back to localhost', () => {
    expect(resolveApiBase({ NODE_ENV: 'development' })).toEqual({
      base: 'http://127.0.0.1:8000',
      configured: true,
    });
  });

  test('production must NOT fall back to localhost', () => {
    const result = resolveApiBase({ NODE_ENV: 'production' });
    expect(result.configured).toBe(false);
    expect(result.base).toBe('');
    expect(result.base).not.toContain('127.0.0.1');
    expect(result.base).not.toContain('localhost');
  });

  test('an empty or whitespace base in production is not a base', () => {
    for (const value of ['', '   ']) {
      expect(resolveApiBase({ NEXT_PUBLIC_API_BASE: value, NODE_ENV: 'production' })).toEqual({
        base: '',
        configured: false,
      });
    }
  });
});
