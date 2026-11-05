import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { Administrators } from '../src/Administrators';
import { SignIn } from '../src/SignIn';
import { api, ApiError } from '../src/api';
import type { AdministratorDirectory, SessionView } from '../src/contracts';

const session: SessionView = { display_name: 'Test operator', workspace_id: 'unit-test-only', expires_at: '2099-01-01T00:00:00Z' };
const directory: AdministratorDirectory = { items: [
  { id: 'recovery-test', display_name: 'Recovery test', email: null, identity_kind: 'local_recovery', status: 'active', authorization_revision: 'r1' },
  { id: 'corporate-test', display_name: 'Corporate test', email: 'corporate@example.test', identity_kind: 'corporate_sso', status: 'active', authorization_revision: 'r2' },
  { id: 'revoked-test', display_name: 'Revoked test', email: 'revoked@example.test', identity_kind: 'corporate_sso', status: 'revoked', authorization_revision: 'r3' },
], page: 1, page_size: 10, pages: 2, total: 13, statistics: { total: 13, active: 12, protected_recovery: 1 } };

// Supply an independent query cache for each component scenario.
function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return { ...render(<QueryClientProvider client={client}>{element}</QueryClientProvider>), client };
}

// Hold asynchronous work to inspect pending states and prevent duplicate actions.
function deferred<T>() {
  let resolve!: (value: T) => void; let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

// Fill only invented unit-test factors; no server request leaves the mocked API.
async function fillSignIn() {
  await userEvent.type(screen.getByLabelText('Password'), 'unit-test-password');
  await userEvent.type(screen.getByLabelText('Authenticator code'), '123456');
}

describe('SignIn', () => {
  // Verify labels, first-time instructions, pending protection and sensitive-field cleanup.
  it('submits one request and clears factors after successful sign-in', async () => {
    const pending = deferred<SessionView>(); const signIn = vi.spyOn(api, 'signIn').mockReturnValue(pending.promise); const success = vi.fn();
    mount(<SignIn onSuccess={success} notice="Session ended" />);
    expect(screen.getByRole('status')).toHaveTextContent('Session ended');
    expect(screen.getByLabelText('Username')).toHaveAttribute('readonly');
    fireEvent.click(screen.getByText('First-time local setup'));
    expect(screen.getByText(/otm-local bootstrap/)).toBeInTheDocument();
    await fillSignIn();
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled());
    fireEvent.submit(screen.getByRole('button').closest('form')!);
    expect(signIn).toHaveBeenCalledTimes(1);
    await act(async () => pending.resolve(session));
    await waitFor(() => expect(success).toHaveBeenCalledWith(session));
    expect(screen.getByLabelText('Password')).toHaveValue('');
    expect(screen.getByLabelText('Authenticator code')).toHaveValue('');
  });

  // Preserve retryable password input and avoid disclosing server diagnostics for rejected factors.
  it.each([401, 503])('announces a safe %s error and clears the one-use code', async status => {
    vi.spyOn(api, 'signIn').mockRejectedValue(new ApiError(status)); mount(<SignIn onSuccess={vi.fn()} notice="" />);
    await fillSignIn(); await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(status === 401 ? 'Sign-in failed' : 'temporarily unavailable');
    expect(screen.getByLabelText('Password')).toHaveValue('unit-test-password');
    expect(screen.getByLabelText('Authenticator code')).toHaveValue('');
  });
});

describe('Administrators', () => {
  // Exercise actual table data, server query changes, filtering and pagination controls.
  it('renders protected grants and sends revised search, sort, page-size and page queries', async () => {
    const read = vi.spyOn(api, 'directory').mockImplementation(async query => ({ ...directory, page: query.page ?? 1, page_size: query.page_size ?? 10 }));
    mount(<Administrators expired={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    expect(await screen.findByText('Corporate test')).toBeInTheDocument();
    expect(screen.getByText('Protected recovery account')).toBeInTheDocument(); expect(screen.getByText('Operator-managed')).toBeInTheDocument();
    expect(screen.getByText('No action')).toBeInTheDocument(); expect(screen.getByText('No email')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add administrator' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /Email/ }));
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'email', direction: 'asc' }), expect.any(AbortSignal)));
    await userEvent.click(screen.getByRole('button', { name: /Email/ }));
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'email', direction: 'desc' }), expect.any(AbortSignal)));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('Page 2 of 2')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await userEvent.selectOptions(screen.getByLabelText('Rows per page'), '25');
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 25 }), expect.any(AbortSignal)));
    await userEvent.type(screen.getByRole('searchbox'), 'Corporate');
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ query: 'Corporate', page: 1 }), expect.any(AbortSignal)));
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(screen.getByText('Showing 1–13 of 13')).toBeInTheDocument();
  });

  // A failed read must remain retryable, and an empty search offers a working reset.
  it('recovers from load failure and clears a no-match search', async () => {
    const read = vi.spyOn(api, 'directory').mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ ...directory, items: [], total: 0, pages: 1 });
    mount(<Administrators expired={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load');
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByText('No administrators match your search')).toBeInTheDocument();
    await userEvent.type(screen.getByRole('searchbox'), 'missing');
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ query: 'missing' }), expect.any(AbortSignal)));
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    await waitFor(() => expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ query: '' }), expect.any(AbortSignal)));
    expect(screen.getByText('0 results')).toBeInTheDocument();
  });

  // Directory authentication failure must invoke the session-expiration boundary.
  it.each([401, 403])('expires the session when the directory returns %s', async status => {
    vi.spyOn(api, 'directory').mockRejectedValue(new ApiError(status)); const expired = vi.fn(); mount(<Administrators expired={expired} />);
    await waitFor(() => expect(expired).toHaveBeenCalled());
  });

  // Cancel and Escape must close the native confirmation without changing a grant.
  it('cancels revocation using both Cancel and native cancel', async () => {
    vi.spyOn(api, 'directory').mockResolvedValue(directory); const revoke = vi.spyOn(api, 'revoke'); const { container } = mount(<Administrators expired={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Revoke' })); const dialog = container.querySelector('dialog')!;
    expect(dialog.open).toBe(true); await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' })); expect(dialog.open).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Revoke' })); fireEvent(dialog, new Event('cancel', { cancelable: true }));
    expect(dialog.open).toBe(false); expect(revoke).not.toHaveBeenCalled();
  });

  // Bind mutation to the displayed revision, suppress duplicates and refresh after completion.
  it('confirms revocation and prevents dismissal while it is pending', async () => {
    vi.spyOn(api, 'directory').mockResolvedValue(directory); const pending = deferred<unknown>(); const revoke = vi.spyOn(api, 'revoke').mockReturnValue(pending.promise);
    const { container } = mount(<Administrators expired={vi.fn()} />); await userEvent.click(await screen.findByRole('button', { name: 'Revoke' }));
    const dialog = container.querySelector('dialog')!; await userEvent.click(within(dialog).getByRole('button', { name: 'Revoke access' }));
    expect(revoke).toHaveBeenCalledWith('corporate-test', 'r2'); await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled());
    fireEvent(dialog, new Event('cancel', { cancelable: true })); expect(dialog.open).toBe(true);
    await act(async () => pending.resolve({})); expect(await screen.findByText('Administrator access revoked.')).toBeInTheDocument(); expect(dialog.open).toBe(false);
  });

  // Distinguish stale authorization from ambiguous failure, while 401 ends the session.
  it.each([409, 503, 401, 403])('handles revocation failure %s without claiming success', async status => {
    vi.spyOn(api, 'directory').mockResolvedValue(directory); vi.spyOn(api, 'revoke').mockRejectedValue(new ApiError(status)); const expired = vi.fn();
    mount(<Administrators expired={expired} />); await userEvent.click(await screen.findByRole('button', { name: 'Revoke' }));
    await userEvent.click(screen.getByRole('button', { name: 'Revoke access' }));
    if (status === 401) await waitFor(() => expect(expired).toHaveBeenCalled());
    else {
      expect(await screen.findByText(status === 409 ? /This administrator changed/ : /Revocation could not be confirmed/)).toBeInTheDocument();
      expect(expired).not.toHaveBeenCalled();
    }
    expect(screen.queryByText('Administrator access revoked.')).not.toBeInTheDocument();
  });
});

describe('App', () => {
  // Do not render authentication controls before a verified session response arrives.
  it('shows session checking and retries a verification outage', async () => {
    const pending = deferred<SessionView | null>(); const verify = vi.spyOn(api, 'session').mockReturnValueOnce(pending.promise).mockResolvedValue(null);
    mount(<App />); expect(screen.getByRole('status')).toHaveTextContent('Checking your session'); await act(async () => pending.reject(new Error('offline')));
    expect(await screen.findByRole('heading', { name: 'Unable to verify your session' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' })); expect(await screen.findByLabelText('Password')).toBeInTheDocument(); expect(verify).toHaveBeenCalledTimes(2);
  });

  // Successful authentication changes the route and logout removes cached privileged data.
  it('signs in, renders the real shell, and clears the administrator cache on logout', async () => {
    history.replaceState(null, '', '/login');
    vi.spyOn(api, 'tenancies').mockResolvedValue({ items: [], total: 0, page: 1, pages: 1, page_size: 10, total_tenancies: 0, individual_count: 0, shared_count: 0, pending_count: 0, issue_count: 0 });
    vi.spyOn(api, 'session').mockResolvedValue(null); vi.spyOn(api, 'signIn').mockResolvedValue(session); vi.spyOn(api, 'directory').mockResolvedValue(directory); vi.spyOn(api, 'logout').mockResolvedValue(undefined);
    const { client } = mount(<App />); await screen.findByLabelText('Password'); await fillSignIn(); await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('heading', { name: 'Tenancies' })).toBeInTheDocument(); expect(location.pathname).toBe('/tenancies');
    await userEvent.click(screen.getByRole('link', { name: /^Administrators$/ }));
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument(); await screen.findByText('Corporate test');
    client.setQueryDefaults(['onboarding'], { gcTime: Infinity }); client.setQueryDefaults(['tenancy-deletion'], { gcTime: Infinity });
    client.setQueryData(['onboarding', 'private'], { owner: 'Synthetic owner' }); client.setQueryData(['tenancy-deletion', 'private'], { people: ['Synthetic member'] });
    expect(client.getQueryData(['onboarding', 'private'])).toBeDefined(); expect(client.getQueryData(['tenancy-deletion', 'private'])).toBeDefined();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' })); expect(await screen.findByText('You have signed out.')).toBeInTheDocument();
    expect(client.getQueriesData({ queryKey: ['onboarding'] })).toEqual([]); expect(client.getQueriesData({ queryKey: ['tenancy-deletion'] })).toEqual([]);
    expect(location.pathname).toBe('/login'); expect(client.getQueriesData({ queryKey: ['administrators'] })).toEqual([]);
  });

  // Ambiguous sign-out must retain the verified session and expose a truthful retry.
  it('retains the session and offers retry after a failed sign-out request', async () => {
    vi.spyOn(api, 'session').mockResolvedValue(session); vi.spyOn(api, 'directory').mockResolvedValue(directory); vi.spyOn(api, 'logout').mockRejectedValue(new Error('offline'));
    mount(<App />); await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Sign-out could not be confirmed. Please try again.');
    expect(screen.getByRole('heading', { name: 'Administrators' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    vi.mocked(api.logout).mockResolvedValue(undefined);
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByText('You have signed out.')).toBeInTheDocument();
  });

  // Unauthorized directory reads use the same signed-out boundary as idle expiration.
  it.each([401, 403])('returns to login and purges cached grants after directory denial %s', async status => {
    vi.spyOn(api, 'session').mockResolvedValue(session); vi.spyOn(api, 'directory').mockRejectedValue(new ApiError(status));
    const { client } = mount(<App />); expect(await screen.findByText('Your session ended. Sign in again.')).toBeInTheDocument();
    expect(client.getQueriesData({ queryKey: ['administrators'] })).toEqual([]);
    expect(client.getQueryData(['session'])).toBeNull();
  });
});

// Delayed reads must never overwrite the authoritative result of a credential transition.
describe('Session response ordering', () => {
  // Cancel an old verified-session poll before publishing signed out, even if transport ignores abort.
  it('ignores a delayed authenticated poll after successful logout', async () => {
    const poll = deferred<SessionView | null>();
    vi.spyOn(api, 'session').mockResolvedValueOnce(session).mockReturnValue(poll.promise);
    vi.spyOn(api, 'directory').mockResolvedValue(directory); vi.spyOn(api, 'logout').mockResolvedValue(undefined);
    const { client } = mount(<App />); await screen.findByRole('heading', { name: 'Administrators' });
    let request!: Promise<void>; act(() => { request = client.refetchQueries({ queryKey: ['session'] }); });
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' })); await screen.findByLabelText('Password');
    await act(async () => { poll.resolve(session); await request; });
    expect(client.getQueryData(['session'])).toBeNull(); expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  // An older signed-out poll cannot clear a newly verified session after sign-in completes.
  it('ignores a delayed unauthenticated poll after fresh sign-in', async () => {
    const poll = deferred<SessionView | null>();
    vi.spyOn(api, 'session').mockResolvedValueOnce(null).mockReturnValue(poll.promise);
    vi.spyOn(api, 'signIn').mockResolvedValue(session); vi.spyOn(api, 'directory').mockResolvedValue(directory);
    const { client } = mount(<App />); await screen.findByLabelText('Password'); await fillSignIn();
    let request!: Promise<void>; act(() => { request = client.refetchQueries({ queryKey: ['session'] }); });
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' })); await screen.findByRole('heading', { name: 'Administrators' });
    await act(async () => { poll.resolve(null); await request; });
    expect(client.getQueryData(['session'])).toEqual(session); expect(screen.getByRole('heading', { name: 'Administrators' })).toBeInTheDocument();
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  // Expiration uses the same race-safe boundary as deliberate logout.
  it('ignores a delayed authenticated poll after a directory expiration', async () => {
    const poll = deferred<SessionView | null>();
    vi.spyOn(api, 'session').mockResolvedValueOnce(session).mockReturnValue(poll.promise);
    const read = vi.spyOn(api, 'directory').mockResolvedValue(directory);
    const { client } = mount(<App />); await screen.findByText('Corporate test');
    let request!: Promise<void>; act(() => { request = client.refetchQueries({ queryKey: ['session'] }); });
    read.mockRejectedValue(new ApiError(401)); await userEvent.click(screen.getByRole('button', { name: 'Refresh' })); await screen.findByLabelText('Password');
    await act(async () => { poll.resolve(session); await request; });
    expect(client.getQueryData(['session'])).toBeNull(); expect(screen.getByText('Your session ended. Sign in again.')).toBeInTheDocument();
  });

  // The server's 503 logout response clears the browser cookie while warning about incomplete server cleanup.
  it('clears the local view after the explicit logout cookie-clearing response', async () => {
    vi.spyOn(api, 'session').mockResolvedValue(session); vi.spyOn(api, 'directory').mockResolvedValue(directory); vi.spyOn(api, 'logout').mockRejectedValue(new ApiError(503));
    mount(<App />); await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
    expect(await screen.findByText('Browser credentials cleared, but server sign-out could not be confirmed.')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });
});

// Large directories keep pagination operable without rendering an unbounded list of controls.
it('shows a bounded numbered page window and supports direct page navigation', async () => {
  vi.spyOn(api, 'directory').mockImplementation(async query => ({ ...directory, page: query.page ?? 1, pages: 20, total: 200 }));
  mount(<Administrators expired={vi.fn()} />); await screen.findByText('Corporate test');
  const pages = screen.getByRole('navigation', { name: 'Administrator pages' });
  expect(within(pages).getAllByRole('button')).toHaveLength(5);
  expect(within(pages).getByRole('button', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page');
  await userEvent.click(within(pages).getByRole('button', { name: 'Page 5' })); await screen.findByText('Page 5 of 20');
  const updated = screen.getByRole('navigation', { name: 'Administrator pages' });
  expect(within(updated).getByRole('button', { name: 'Page 3' })).toBeInTheDocument();
  expect(within(updated).getByRole('button', { name: 'Page 7' })).toBeInTheDocument();
});

// A verified session at the site root opens inventory without replacing deliberate feature paths.
it('opens Tenancies from the root URL', async () => {
  history.replaceState(null, '', '/');
  vi.spyOn(api, 'session').mockResolvedValue(session);
  vi.spyOn(api, 'tenancies').mockResolvedValue({ items: [], total: 0, page: 1, pages: 1, page_size: 10, total_tenancies: 0, individual_count: 0, shared_count: 0, pending_count: 0, issue_count: 0 });
  mount(<App />);
  await screen.findByRole('heading', { name: /^Tenancies$/ });
  expect(location.pathname).toBe('/tenancies');
});
