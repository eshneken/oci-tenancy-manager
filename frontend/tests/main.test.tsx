import { expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import { api } from '../src/api';

// Verify the shipped entry point infrastructure-services providers and mounts into the actual root element.
it('mounts the application through its production entry point', async () => {
  vi.spyOn(api, 'session').mockResolvedValue(null);
  const root = document.createElement('div'); root.id = 'root'; document.body.append(root);
  await act(async () => { await import('../src/main'); });
  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  root.remove();
});
