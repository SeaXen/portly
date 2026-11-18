import { describe, it, expect, vi, afterEach } from 'vitest';
import { api } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('api.request', () => {
  it('dispatches portly:unauthorized and throws the server message on 401', async () => {
    const listener = vi.fn();
    window.addEventListener('portly:unauthorized', listener);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 401,
        ok: false,
        statusText: 'Unauthorized',
        json: async () => ({ detail: { message: 'Not authenticated', code: 'UNAUTHORIZED' } }),
      })
    );

    await expect(api.getStats()).rejects.toMatchObject({
      message: 'Not authenticated',
      code: 'UNAUTHORIZED',
    });
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener('portly:unauthorized', listener);
  });

  it('throws the parsed error for other non-OK responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        status: 500,
        ok: false,
        statusText: 'Server Error',
        json: async () => ({ detail: { message: 'Boom' } }),
      })
    );

    await expect(api.getStats()).rejects.toMatchObject({ message: 'Boom' });
    expect(fetch).toHaveBeenCalledWith('/api/stats', expect.objectContaining({
      headers: expect.objectContaining({ 'X-Portly-Client': '1' }),
    }));
  });
});
