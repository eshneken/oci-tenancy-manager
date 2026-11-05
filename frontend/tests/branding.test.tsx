import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { Brand, defaultBranding, useBranding } from '../src/Branding';
import { App } from '../src/App';
import { api, ApiError } from '../src/api';
import type { BrandingView } from '../src/contracts';

const atlas: BrandingView = { display_name: 'Atlas', logo_url: '/branding-assets/atlas-wordmark.png', icon_url: '/branding-assets/atlas-icon.png' };

// Keep the public branding request and its cache independent from every authentication scenario.
function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return { ...render(<QueryClientProvider client={client}>{element}</QueryClientProvider>), client };
}

// Exercise the same public request, fallback, document identity and shared logo used by the app shell.
function BrandedView() {
  const branding = useBranding();
  return <Brand branding={branding} />;
}

describe('Instance branding', () => {
  // Configured branding is used before authentication, and mounted document assets are cleaned up.
  it('uses a runtime name, logo and browser icon without hardcoding the installation', async () => {
    document.title = 'Original title';
    vi.spyOn(api, 'branding').mockResolvedValue(atlas);
    const view = mount(<BrandedView />);
    const image = await screen.findByRole('img', { name: 'Atlas' });
    expect(image).toHaveAttribute('src', atlas.logo_url);
    expect(document.title).toBe('Atlas');
    expect(document.head.querySelector('link[data-application-branding]')).toHaveAttribute('href', atlas.icon_url);
    view.unmount();
    expect(document.title).toBe('Original title');
    expect(document.head.querySelector('link[data-application-branding]')).toBeNull();
  });

  // A branding outage is cosmetic and must never remove an otherwise verified administrator session.
  it.each([401, 503])('keeps a verified session when public branding returns %s', async status => {
    vi.spyOn(api, 'branding').mockRejectedValue(new ApiError(status));
    const session = { display_name: 'Synthetic operator', workspace_id: 'branding-unit', expires_at: '2099-01-01T00:00:00Z' };
    vi.spyOn(api, 'session').mockResolvedValue(session);
    vi.spyOn(api, 'directory').mockResolvedValue({ items: [], total: 0, pages: 1, page: 1, page_size: 10, statistics: { total: 0, active: 0, protected_recovery: 0 } });
    const { client } = mount(<App />);
    expect(await screen.findByRole('heading', { name: 'Administrators' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: defaultBranding.display_name })).toBeInTheDocument();
    expect(client.getQueryData(['session'])).toEqual(session);
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
  });

  // Broken or absent brand assets leave a readable accessible configured application name.
  it('falls back to the display name for a failed logo and permits a later different logo', () => {
    const view = render(<Brand branding={atlas} />);
    fireEvent.error(screen.getByRole('img', { name: 'Atlas' }));
    expect(screen.getByText('Atlas')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    view.rerender(<Brand branding={{ ...atlas, logo_url: '/branding-assets/replacement.webp' }} />);
    expect(screen.getByRole('img', { name: 'Atlas' })).toHaveAttribute('src', '/branding-assets/replacement.webp');
    view.rerender(<Brand branding={{ ...atlas, logo_url: null }} />);
    expect(screen.getByText('Atlas')).toBeInTheDocument();
  });

  // Untrusted strings are text, and neither external images nor executable URLs enter the document.
  it('renders text safely and rejects external or executable asset locations', async () => {
    const name = '<img src=x onerror=alert(1)>';
    vi.spyOn(api, 'branding').mockResolvedValue({ display_name: name, logo_url: 'https://external.example.test/logo.png', icon_url: 'javascript:alert(1)' });
    const view = mount(<BrandedView />);
    expect(await screen.findByText(name)).toBeInTheDocument();
    expect(view.container.querySelector('img')).toBeNull();
    expect(document.title).toBe(name);
    expect(document.head.querySelector('link[data-application-branding]')).toBeNull();
  });

  // Sign-in uses exactly the same runtime brand as the authenticated navigation shell.
  it('shows instance branding on the unauthenticated sign-in screen', async () => {
    vi.spyOn(api, 'branding').mockResolvedValue(atlas);
    vi.spyOn(api, 'session').mockResolvedValue(null);
    mount(<App />);
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Atlas' })).toContainElement(screen.getByRole('img', { name: 'Atlas' }));
  });

  // Runtime public configuration can change without a rebuilt bundle or an authentication transition.
  it('replaces the title and favicon on refetch without accumulating old icons', async () => {
    vi.spyOn(api, 'branding').mockResolvedValue(atlas);
    const view = mount(<BrandedView />);
    await screen.findByRole('img', { name: 'Atlas' });
    await act(async () => { view.client.setQueryData(['branding'], { display_name: 'Another team', logo_url: null, icon_url: null }); });
    expect(await screen.findByText('Another team')).toBeInTheDocument();
    expect(document.title).toBe('Another team');
    expect(document.head.querySelector('link[data-application-branding]')).toBeNull();
    await waitFor(() => expect(view.client.getQueryData(['branding'])).toMatchObject({ display_name: 'Another team' }));
  });
});
