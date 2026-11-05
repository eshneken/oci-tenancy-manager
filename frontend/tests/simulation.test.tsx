import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SimulationInspection } from '../src/SimulationInspection';
import { Operations } from '../src/Operations';
import { api, ApiError } from '../src/api';
import type { OperationDetail, OperationDirectory } from '../src/contracts';

const target = 'ocid1.tenancy.oc1..unit-synthetic-healthy';
const otherTarget = 'ocid1.tenancy.oc1..unit-synthetic-timeout';
const catalog = { provider_mode: 'simulated' as const, execution_paused: false, targets: [
  { tenancy_ocid: target, name: 'Unit healthy target', scenario: 'healthy' as const },
  { tenancy_ocid: otherTarget, name: 'Unit timeout target', scenario: 'timeout' as const },
] };
const operationId = '22222222-2222-4222-8222-222222222222';
const accepted = { operation_id: operationId, state: 'queued' as const, accepted_at: '2026-10-30T12:00:00Z' };

// Give submission and polling tests their own cache, independent of the database and browser session.
function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return { ...render(<QueryClientProvider client={client}>{element}</QueryClientProvider>), client };
}

// Keep transport in flight to inspect native confirmation and duplicate-submission guards.
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }

// Open only the actual confirmation control and explicitly choose a configured synthetic target.
async function chooseTarget() {
  await userEvent.click(await screen.findByRole('button', { name: 'Run simulated inspection' }));
  await userEvent.selectOptions(screen.getByLabelText('Synthetic target'), target);
  return screen.getByRole('dialog');
}

// Default discovery is simulated and available; individual scenarios override only their relevant outcome.
beforeEach(() => { vi.spyOn(api, 'inspectionSandbox').mockResolvedValue(catalog); });

describe('Explicit simulated inspection admission', () => {
  // No speculative submission control appears while availability is unknown or the feature is absent.
  it('hides the control while discovery is pending and after explicit 404', async () => {
    const pending = deferred<typeof catalog>(); vi.mocked(api.inspectionSandbox).mockReturnValueOnce(pending.promise);
    const view = mount(<SimulationInspection expired={vi.fn()} navigate={vi.fn()} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument(); view.unmount();
    vi.mocked(api.inspectionSandbox).mockRejectedValue(new ApiError(404)); mount(<SimulationInspection expired={vi.fn()} navigate={vi.fn()} />);
    await waitFor(() => expect(api.inspectionSandbox).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('button')).not.toBeInTheDocument(); expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  // Paused execution and an empty configured catalog remain clear unavailable states.
  it.each(['paused', 'empty'])('disables admission when %s', async state => {
    vi.mocked(api.inspectionSandbox).mockResolvedValue({ ...catalog, execution_paused: state === 'paused', targets: state === 'empty' ? [] : catalog.targets });
    mount(<SimulationInspection expired={vi.fn()} navigate={vi.fn()} />);
    expect(await screen.findByRole('button', { name: 'Run simulated inspection' })).toBeDisabled();
    expect(screen.getByText(state === 'paused' ? 'Simulated inspection execution is paused.' : 'No simulated targets are configured.')).toBeInTheDocument();
  });

  // A catalog service outage leaves existing operation reads available and offers a scoped retry.
  it('retries availability separately from the recorded-operation list', async () => {
    vi.mocked(api.inspectionSandbox).mockRejectedValueOnce(new ApiError(503)).mockResolvedValue(catalog);
    mount(<SimulationInspection expired={vi.fn()} navigate={vi.fn()} />);
    expect(await screen.findByRole('status')).toHaveTextContent('availability could not be checked');
    await userEvent.click(screen.getByRole('button', { name: 'Retry availability' }));
    expect(await screen.findByRole('button', { name: 'Run simulated inspection' })).toBeEnabled();
  });

  // Read denials terminate the privileged view instead of presenting a service-retry loop.
  it.each([401, 403])('expires access after catalog status %s', async status => {
    const expired = vi.fn(); vi.mocked(api.inspectionSandbox).mockRejectedValue(new ApiError(status));
    mount(<SimulationInspection expired={expired} navigate={vi.fn()} />); await waitFor(() => expect(expired).toHaveBeenCalled());
  });

  // Cancel and Escape perform no admission, and a missing target cannot be submitted programmatically.
  it('requires an explicit target and cancels without creating work', async () => {
    const inspect = vi.spyOn(api, 'inspect'); mount(<SimulationInspection expired={vi.fn()} navigate={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Run simulated inspection' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus();
    expect(within(dialog).getByText(/makes no OCI calls/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Run simulated inspection' })).toBeDisabled();
    fireEvent.submit(dialog.querySelector('form')!); expect(inspect).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' })); expect((dialog as HTMLDialogElement).open).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Run simulated inspection' })); fireEvent(dialog, new Event('cancel', { cancelable: true }));
    expect((dialog as HTMLDialogElement).open).toBe(false); expect(inspect).not.toHaveBeenCalled();
  });

  // Admission binds only the exact selected synthetic OCID and one opaque key, then opens recorded progress.
  it('holds pending confirmation, blocks duplicates, invalidates list and navigates only after acceptance', async () => {
    const pending = deferred<typeof accepted>(); const inspect = vi.spyOn(api, 'inspect').mockReturnValue(pending.promise); const navigate = vi.fn();
    const { client } = mount(<SimulationInspection expired={vi.fn()} navigate={navigate} />); const invalidate = vi.spyOn(client, 'invalidateQueries');
    const dialog = await chooseTarget(); const form = dialog.querySelector('form')!;
    act(() => { fireEvent.submit(form); fireEvent.submit(form); });
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Submitting…' })).toBeDisabled());
    expect(screen.getByLabelText('Synthetic target')).toBeDisabled(); expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
    fireEvent(dialog, new Event('cancel', { cancelable: true })); expect((dialog as HTMLDialogElement).open).toBe(true);
    expect(inspect).toHaveBeenCalledTimes(1); expect(inspect).toHaveBeenCalledWith({ tenancy_ocid: target, client_request_key: expect.stringMatching(/^[0-9a-f-]{36}$/) }); expect(navigate).not.toHaveBeenCalled();
    await act(async () => pending.resolve(accepted));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['operations', 'list'] }); expect(navigate).toHaveBeenCalledWith('/operations/' + operationId); expect((dialog as HTMLDialogElement).open).toBe(false);
  });

  // An ambiguous response must retain the request identity across retries and dialog dismissal.
  it('reuses the same key after uncertain submission and gives each new target a separate identity', async () => {
    const inspect = vi.spyOn(api, 'inspect').mockRejectedValueOnce(new ApiError(503)).mockRejectedValueOnce(new TypeError('offline')).mockResolvedValue(accepted);
    mount(<SimulationInspection expired={vi.fn()} navigate={vi.fn()} />); const dialog = await chooseTarget();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Run simulated inspection' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to confirm submission. Check Operations before starting another request.');
    const firstKey = inspect.mock.calls[0][0].client_request_key;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await userEvent.click(screen.getByRole('button', { name: 'Run simulated inspection' }));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Check submission again' }));
    await screen.findByRole('alert'); expect(inspect.mock.calls[1][0].client_request_key).toBe(firstKey);
    await userEvent.selectOptions(screen.getByLabelText('Synthetic target'), otherTarget);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument(); expect(screen.getByText('Scenario: Timeout')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Synthetic target'), target);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Run simulated inspection' }));
    await waitFor(() => expect(inspect).toHaveBeenCalledTimes(3)); expect(inspect.mock.calls[2][0].client_request_key).toBe(firstKey);
  });

  // Rejected requests use fixed guidance, while authenticated-read denial ends access.
  it.each([400, 409, 401, 403])('handles submission status %s without claiming a completed inspection', async status => {
    const expired = vi.fn(); vi.spyOn(api, 'inspect').mockRejectedValue(new ApiError(status));
    mount(<SimulationInspection expired={expired} navigate={vi.fn()} />); const dialog = await chooseTarget();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Run simulated inspection' }));
    if (status === 401 || status === 403) await waitFor(() => expect(expired).toHaveBeenCalled());
    else expect(await screen.findByRole('alert')).toHaveTextContent(status === 400 ? 'This inspection request could not be accepted.' : 'This request conflicts with recorded work.');
    expect(screen.queryByText(/Inspection completed successfully/)).not.toBeInTheDocument();
  });
});

describe('Read-only operation status polling', () => {
  // List refresh reads must not dispatch work or count as user activity.
  it('polls the list every 15 seconds without submitting or renewing activity', async () => {
    vi.useFakeTimers(); vi.mocked(api.inspectionSandbox).mockRejectedValue(new ApiError(404));
    const data: OperationDirectory = { items: [], total: 0, page: 1, page_size: 10, pages: 1 };
    const read = vi.spyOn(api, 'operations').mockResolvedValue(data); const activity = vi.spyOn(api, 'activity'); const inspect = vi.spyOn(api, 'inspect');
    mount(<Operations operationId={null} expired={vi.fn()} navigate={vi.fn()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); }); expect(read).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); }); expect(read).toHaveBeenCalledTimes(2);
    expect(activity).not.toHaveBeenCalled(); expect(inspect).not.toHaveBeenCalled();
  });

  // Active detail states poll until a terminal result arrives, then stop without mutating the operation.
  it.each(['queued', 'running', 'waiting'] as const)('polls %s detail every 5 seconds and stops after success', async state => {
    vi.useFakeTimers();
    const operation: OperationDetail['operation'] = { id: operationId, kind: 'inspect_import', state, stage: 'inspect_target', accepted_at: accepted.accepted_at, updated_at: accepted.accepted_at, completed_at: null, initiated_by: null, target_tenancy_ocid: target, provider_mode: 'simulated' };
    const read = vi.spyOn(api, 'operation').mockResolvedValueOnce({ operation, steps: [], events: [], events_limited: false }).mockResolvedValue({ operation: { ...operation, state: 'succeeded' }, steps: [], events: [], events_limited: false });
    const activity = vi.spyOn(api, 'activity'); mount(<Operations operationId={operationId} expired={vi.fn()} navigate={vi.fn()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); }); expect(read).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(5_001); }); expect(read).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); }); expect(read).toHaveBeenCalledTimes(2); expect(activity).not.toHaveBeenCalled();
  });
});
