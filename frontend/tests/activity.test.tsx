import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useActivity } from '../src/activity';
import { api, ApiError } from '../src/api';

// Mount the hook without introducing DOM controls or changing production state.
function Activity({ enabled, expired }: { enabled: boolean; expired: () => void }) { useActivity(enabled, expired); return null; }

describe('Activity renewal', () => {
  // Synthetic events cannot extend authenticated sessions and disabled hooks do not subscribe.
  it('ignores synthetic input and cleans up its document subscriptions', () => {
    const activity = vi.spyOn(api, 'activity'); const add = vi.spyOn(document, 'addEventListener'); const remove = vi.spyOn(document, 'removeEventListener');
    const view = render(<Activity enabled={false} expired={vi.fn()} />); expect(add.mock.calls.filter(([name]) => name === 'pointerdown')).toHaveLength(0);
    view.rerender(<Activity enabled expired={vi.fn()} />);
    document.dispatchEvent(new Event('pointerdown')); document.dispatchEvent(new Event('keydown')); expect(activity).not.toHaveBeenCalled();
    view.unmount(); expect(remove).toHaveBeenCalledWith('pointerdown', expect.any(Function)); expect(remove).toHaveBeenCalledWith('keydown', expect.any(Function));
  });

  // Drive the registered handler directly to cover trusted-input timing without forging browser UI events.
  it('throttles trusted input and invokes the latest expiry callback only for 401', async () => {
    let now = 100_000; vi.spyOn(Date, 'now').mockImplementation(() => now);
    const add = vi.spyOn(document, 'addEventListener'); const activity = vi.spyOn(api, 'activity').mockResolvedValue({ display_name: null, workspace_id: 'unit', expires_at: '' });
    const first = vi.fn(); const latest = vi.fn(); const view = render(<Activity enabled expired={first} />);
    const handler = add.mock.calls.find(([name]) => name === 'pointerdown')![1] as (event: Event) => void;
    const trustedInput = { isTrusted: true } as Event; handler(trustedInput); expect(activity).not.toHaveBeenCalled();
    now += 60_000; await act(async () => handler(trustedInput)); expect(activity).toHaveBeenCalledTimes(1);
    handler(trustedInput); expect(activity).toHaveBeenCalledTimes(1);
    view.rerender(<Activity enabled expired={latest} />);
    activity.mockRejectedValueOnce(new ApiError(503)); now += 60_000; await act(async () => handler(trustedInput)); expect(latest).not.toHaveBeenCalled();
    activity.mockRejectedValueOnce(new ApiError(401)); now += 60_000; await act(async () => handler(trustedInput)); expect(latest).toHaveBeenCalledOnce(); expect(first).not.toHaveBeenCalled();
  });
});
